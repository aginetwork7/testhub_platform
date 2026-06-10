/**
 * 配置同步脚本
 * 从 config.yaml 生成前端 .env 文件
 */
const fs = require('fs')
const path = require('path')
const yaml = require('js-yaml')

// 读取 config.yaml
const configPath = path.resolve(__dirname, '../../config.yaml')
const envPath = path.resolve(__dirname, '../.env')

console.log('读取配置文件:', configPath)

try {
  const configContent = fs.readFileSync(configPath, 'utf8')
  const config = yaml.load(configContent)
  const frontendPortOverride = process.env.VITE_FRONTEND_PORT || process.env.FRONTEND_PORT
  const apiBaseUrlOverride = process.env.VITE_API_BASE_URL || process.env.FRONTEND_API_BASE_URL

  // 生成 .env 文件内容
  let envContent = ''

  // 服务器配置
  if (frontendPortOverride) {
    envContent += `VITE_FRONTEND_PORT=${frontendPortOverride}\n`
  } else if (config.server && config.server.frontend_port) {
      envContent += `VITE_FRONTEND_PORT=${config.server.frontend_port}\n`
  }

  if (apiBaseUrlOverride) {
    envContent += `VITE_API_BASE_URL=${apiBaseUrlOverride}\n`
  } else if (config.server && config.server.backend_host && config.server.backend_port) {
      envContent += `VITE_API_BASE_URL=http://${config.server.backend_host}:${config.server.backend_port}\n`
  }

  // 写入 .env 文件
  fs.writeFileSync(envPath, envContent, 'utf8')
  console.log('✓ 前端 .env 文件已生成:', envPath)
  console.log('配置内容:')
  console.log(envContent)

} catch (error) {
  console.error('生成 .env 文件失败:', error.message)
  process.exit(1)
}
