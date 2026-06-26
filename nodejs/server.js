require('dotenv').config(); // .env 파일에서 환경 변수 로드
const http = require('http');
const fs = require('fs');
const path = require('path');
const querystring = require('querystring'); // form 데이터 파싱을 위해

const PORT = 3030;
const HOST = '0.0.0.0';

// .env 파일에서 사용자 정보를 가져오거나 기본값을 사용
const FAKE_USER = process.env.USER || 'admin';
const FAKE_PASSWORD = process.env.PASSWORD || 'password123';
const SESSION_KEY = 'sessionId';
const SESSION_VALUE = 'secret-session-id-for-demo'; // 실제 환경에서는 암호화된 랜덤 값 사용

/**
 * 쿠키 파싱 함수
 */
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

/**
 * 파일 서빙 함수 (환경변수 주입 기능 추가)
 */
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

  // 라우팅 로직
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
  
  // [핵심 수정] 파일 직접 읽기 구조로 변경된 API 엔드포인트
  else if (req.url === '/api/macro' && req.method === 'GET') {
    if (!isLoggedIn) {
      res.writeHead(401);
      res.end('Unauthorized');
      return;
    }
    
    // 파이썬을 실행(exec)하는 로직을 완전히 제거했습니다.
    // giup-python 컨테이너가 10분마다 만들어두는 도커 내부의 절대경로 파일만 순수하게 읽어옵니다.
    const dataFilePath = '/data/macro_data.json';
    
    fs.readFile(dataFilePath, 'utf8', (err, data) => {
      if (err) {
          console.error("Data File Read Error:", err);
          res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ error: '백그라운드에서 데이터를 수집 중입니다. 10초 뒤에 새로고침 해주세요.' }));
          return;
      }
      
      // 읽어온 json 파일 내용을 그대로 브라우저로 전송
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(data);
    });
    
  } else {
    res.writeHead(404);
    res.end('Not Found');
  }
});

server.listen(PORT, HOST, () => {
  console.log(`서버가 http://${HOST}:${PORT} 에서 실행 중입니다.`);
});