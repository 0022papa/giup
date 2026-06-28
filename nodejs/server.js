require('dotenv').config(); // .env 파일에서 환경 변수 로드
const http = require('http');
const fs = require('fs');
const path = require('path');
const querystring = require('querystring'); // form 데이터 파싱을 위해

const PORT = 3030;
const HOST = '0.0.0.0';

let VALID_USERS = {};

try {
  if (process.env.VALID_USERS) {
    VALID_USERS = JSON.parse(process.env.VALID_USERS);
  } else {
    // .env에 설정이 누락되었을 때 사용할 기본 계정
    VALID_USERS = { 'admin': 'password123' };
  }
} catch (error) {
  console.error(".env 파일의 VALID_USERS 형식이 올바르지 않습니다. JSON 형식을 확인해주세요:", error);
  VALID_USERS = { 'admin': 'password123' }; // 파싱 에러 시 기본 계정 적용
}

// 하위 호환성 유지: 기존처럼 단일 USER, PASSWORD가 .env에 있다면 추가
if (process.env.USER && process.env.PASSWORD) {
  VALID_USERS[process.env.USER] = process.env.PASSWORD;
}

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
      
      if (VALID_USERS[username] && VALID_USERS[username] === password) {
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
  // [추가] 종목 리스트 API 엔드포인트
  else if (req.url === '/api/stocks' && req.method === 'GET') {
    if (!isLoggedIn) {
      res.writeHead(401);
      res.end('Unauthorized');
      return;
    }
    const stockFilePath = '/data/stock_list.json';
    fs.readFile(stockFilePath, 'utf8', (err, data) => {
      if (err) {
        console.error("Stock File Read Error:", err);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify([]));
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(data);
      }
    });
  }
  else if (req.url.startsWith('/api/macro') && req.method === 'GET') {
    if (!isLoggedIn) {
      res.writeHead(401);
      res.end('Unauthorized');
      return;
    }
    
    const dataFilePath = '/data/macro_data.json';
    const flagFilePath = '/data/force_refresh.flag'; 
    
    const parsedUrl = new URL(req.url, `http://${req.headers.host}`);
    const isForce = parsedUrl.searchParams.get('force') === 'true';

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
        fs.writeFile(flagFilePath, '1', (err) => {
            if (err) {
                console.error("플래그 파일 생성 실패", err);
                return sendData();
            }
            
            let checkCount = 0;
            const checkInterval = setInterval(() => {
                checkCount++;
                if (!fs.existsSync(flagFilePath) || checkCount > 30) {
                    clearInterval(checkInterval);
                    sendData(); 
                }
            }, 500);
        });
    } else {
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