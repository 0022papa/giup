require('dotenv').config();
const http = require('http');
const fs = require('fs');
const path = require('path');
const querystring = require('querystring');

const PORT = 3030;
const HOST = '0.0.0.0';

let VALID_USERS = {};

try {
  if (process.env.VALID_USERS) {
    VALID_USERS = JSON.parse(process.env.VALID_USERS);
  } else {
    VALID_USERS = { 'admin': 'password123' };
  }
} catch (error) {
  console.error(".env 파일의 VALID_USERS 형식이 올바르지 않습니다. JSON 형식을 확인해주세요:", error);
  VALID_USERS = { 'admin': 'password123' }; 
}

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
  
  else if (req.url === '/api/stocks' && req.method === 'GET') {
    if (!isLoggedIn) {
      res.writeHead(401);
      res.end('Unauthorized');
      return;
    }
    const stockFilePath = '/data/stock_list.json';
    fs.readFile(stockFilePath, 'utf8', (err, data) => {
      if (err) {
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify([]));
      } else {
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(data);
      }
    });
  }
  
  // [수정] 파일 기반 통신(IPC)으로 파이썬 봇에 작업을 지시하는 라우트
  else if (req.url.startsWith('/api/valuation') && req.method === 'GET') {
    if (!isLoggedIn) {
      res.writeHead(401);
      res.end('Unauthorized');
      return;
    }
    
    const parsedUrl = new URL(req.url, `http://${req.headers.host}`);
    const stock = parsedUrl.searchParams.get('stock');
    
    if (!stock) {
      res.writeHead(400);
      res.end(JSON.stringify({ error: '종목명이 입력되지 않았습니다.' }));
      return;
    }

    const reqFile = '/data/val_request.json';
    const resFile = '/data/val_result.json';

    // 1. 혹시 남아있을 수 있는 이전 결과 파일 미리 삭제
    if (fs.existsSync(resFile)) {
        try { fs.unlinkSync(resFile); } catch(e) {}
    }

    // 2. 파이썬 봇에게 처리할 종목을 파일로 전달
    fs.writeFile(reqFile, JSON.stringify({ stock: stock, time: Date.now() }), 'utf8', (err) => {
      if (err) {
          res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
          res.end(JSON.stringify({ error: '분석 요청을 전달하지 못했습니다.' }));
          return;
      }

      let attempts = 0;
      const maxAttempts = 40; // 최대 20초 (500ms * 40번) 대기
      
      // 3. 0.5초마다 파이썬 봇이 분석을 완료하고 결과 파일을 생성했는지 폴링(Polling)
      const checkInterval = setInterval(() => {
          attempts++;
          
          if (fs.existsSync(resFile)) {
              clearInterval(checkInterval);
              fs.readFile(resFile, 'utf8', (err, data) => {
                  // 결과 확인 후 파일 즉시 삭제
                  try { fs.unlinkSync(resFile); } catch(e) {}
                  
                  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
                  if (err) {
                      res.end(JSON.stringify({ error: '분석 결과를 서버에서 읽어오지 못했습니다.' }));
                  } else {
                      res.end(data);
                  }
              });
          } else if (attempts >= maxAttempts) {
              // 응답 지연 시 타임아웃 처리
              clearInterval(checkInterval);
              try { fs.unlinkSync(reqFile); } catch(e) {} // 요청 취소
              res.writeHead(504, { 'Content-Type': 'application/json; charset=utf-8' });
              res.end(JSON.stringify({ error: '파이썬 봇 응답 지연 (분석 시간이 초과되었습니다).' }));
          }
      }, 500);
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