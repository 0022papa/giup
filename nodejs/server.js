require('dotenv').config(); // .env 파일에서 환경 변수 로드
const http = require('http');
const fs = require('fs');
const path = require('path');
const querystring = require('querystring'); // form 데이터 파싱을 위해

const PORT = 3030;
const HOST = '0.0.0.0';

const FAKE_USER = process.env.USER || 'admin';
const FAKE_PASSWORD = process.env.PASSWORD || 'password123';
const SESSION_KEY = 'sessionId';
const SESSION_VALUE = 'secret-session-id-for-demo'; 

const parseCookies = (cookieHeader) => {
  const list = {};
  if (!cookieHeader) return list;

  cookieHeader.split(';').forEach(function(cookie) {
    let [ name, ...rest] = cookie.split('=');
    name = name?.trim();
    if (!name) return;
    const value = rest.join('=').trim();
    if (!value) return;
    list[name] = decodeURIComponent(value);
  });

  return list;
};

const serveFile = (res, fileName, contentType, shouldInjectEnv = false) => {
  const filePath = path.join(__dirname, fileName);
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(500);
      res.end(`Error loading ${fileName}`);
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      
      if (shouldInjectEnv) {
        let htmlData = data.toString('utf8');
        htmlData = htmlData.replace(
          /{{STOCKDIO_APP_KEY}}/g, 
          process.env.STOCKDIO_APP_KEY || ''
        );
        res.end(htmlData);
      } else {
        res.end(data);
      }
    }
  });
};

const server = http.createServer((req, res) => {
  const cookies = parseCookies(req.headers.cookie);
  const isLoggedIn = cookies[SESSION_KEY] === SESSION_VALUE;

  if (req.url === '/' || req.url === '/index.html') {
    if (isLoggedIn) {
      serveFile(res, 'index.html', 'text/html; charset=utf-8', true);
    } else {
      res.writeHead(302, { 'Location': '/login' });
      res.end();
    }
  } else if (req.url === '/login' && req.method === 'GET') {
    serveFile(res, 'login.html', 'text/html; charset=utf-8');
  } else if (req.url === '/login' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => {
      body += chunk.toString();
    });
    req.on('end', () => {
      const { username, password } = querystring.parse(body);
      if (username === FAKE_USER && password === FAKE_PASSWORD) {
        res.writeHead(302, {
          'Set-Cookie': `${SESSION_KEY}=${SESSION_VALUE}; HttpOnly; Path=/`,
          'Location': '/'
        });
        res.end();
      } else {
        res.writeHead(302, { 'Location': '/login' });
        res.end();
      }
    });
  } else if (req.url === '/logout') {
    res.writeHead(302, {
      'Set-Cookie': `${SESSION_KEY}=; HttpOnly; Path=/; Max-Age=0`,
      'Location': '/login'
    });
    res.end();
  } 
  
  // [수정된 핵심 부분] 강제 갱신 요청 처리 및 플래그 통신 로직
  else if (req.url.startsWith('/api/macro') && req.method === 'GET') {
    if (!isLoggedIn) {
      res.writeHead(401);
      res.end('Unauthorized');
      return;
    }
    
    const dataFilePath = '/data/macro_data.json';
    const flagFilePath = '/data/force_refresh.flag'; 
    
    // URL에서 새로고침 유무(force=true) 파라미터를 읽어옵니다.
    const parsedUrl = new URL(req.url, `http://${req.headers.host}`);
    const isForce = parsedUrl.searchParams.get('force') === 'true';

    // JSON 파일을 읽어 브라우저로 응답하는 공통 함수
    const sendData = () => {
        fs.readFile(dataFilePath, 'utf8', (err, data) => {
            if (err) {
                console.error("Data File Read Error:", err);
                res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
                res.end(JSON.stringify({ error: '백그라운드에서 데이터를 수집 중입니다. 잠시 후 새로고침 해주세요.' }));
                return;
            }
            const sanitizedData = data.replace(/\bNaN\b/g, "null");
            res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(sanitizedData);
        });
    };

    if (isForce) {
        // [추가] 브라우저 최초 접근/새로고침 시 플래그 파일을 생성하여 파이썬 봇을 깨웁니다.
        fs.writeFile(flagFilePath, '1', (err) => {
            if (err) {
                console.error("플래그 파일 생성 실패", err);
                return sendData();
            }
            
            // 파이썬 데몬이 데이터를 갱신하고 플래그 파일을 삭제할 때까지 기다립니다.
            let checkCount = 0;
            const checkInterval = setInterval(() => {
                checkCount++;
                // 파일이 삭제되었거나(수집 성공), 15초(30회)가 초과되면 대기를 멈춥니다.
                if (!fs.existsSync(flagFilePath) || checkCount > 30) {
                    clearInterval(checkInterval);
                    sendData(); // 새로 수집된 데이터를 브라우저에 뿌려줍니다.
                }
            }, 500);
        });
    } else {
        // 강제 갱신이 아닌 일반 타이머 호출일 경우 대기 없이 캐시된 파일만 즉시 전송
        sendData();
    }
    
  } else {
    res.writeHead(404);
    res.end('Not Found');
  }
});

server.listen(PORT, HOST, () => {
  console.log(`서버가 http://${HOST}:${PORT} 에서 실행 중입니다.`);
});