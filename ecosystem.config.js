const fs = require('fs');
const path = require('path');

/**
 * 自动检测项目目录下的 Python 虚拟环境解释器（兼容 macOS / Linux / Windows）
 */
function resolvePythonInterpreter() {
  const isWin = process.platform === 'win32';
  const candidates = isWin
    ? [
        path.join(__dirname, '.venv', 'Scripts', 'python.exe'),
        path.join(__dirname, 'venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.join(__dirname, '.venv', 'bin', 'python'),
        path.join(__dirname, 'venv', 'bin', 'python'),
      ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return isWin ? 'python' : 'python3';
}

module.exports = {
  apps: [
    {
      name: 'weibo-console',
      script: 'service.py',
      interpreter: resolvePythonInterpreter(),
      args: '--host 0.0.0.0 --port 15001',
      cwd: __dirname,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        PYTHONUNBUFFERED: '1',
      },
    },
  ],
};
