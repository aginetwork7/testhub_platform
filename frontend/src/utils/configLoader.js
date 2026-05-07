/**
 * 配置加载器
 * 用于从 YAML 配置文件加载配置
 */

class ConfigLoader {
  constructor() {
    this.config = this._loadConfig()
  }

  _loadConfig() {
    try {
      // 尝试从项目根目录加载 config.yaml
      const response = fetch('/config.yaml')
      if (!response.ok) {
        console.warn('无法加载 config.yaml，使用默认配置')
        return {}
      }
      const yamlText = await response.text()
      return this._parseYAML(yamlText)
    } catch (error) {
      console.warn('加载配置文件失败:', error)
      return {}
    }
  }

  _parseYAML(yamlText) {
    // 简单的 YAML 解析器（仅支持基本格式）
    const lines = yamlText.split('\n')
    const config = {}
    let currentSection = null
    let currentList = null

    for (let line of lines) {
      line = line.trim()
      
      // 跳过注释和空行
      if (!line || line.startsWith('#')) {
        continue
      }

      // 检查是否是章节标题
      if (line.startsWith('# ')) {
        const sectionName = line.substring(2).trim()
        if (sectionName.includes(':')) {
          const [key, value] = sectionName.split(':').map(s => s.trim())
          config[key] = {}
          currentSection = config[key]
          currentList = null
        }
        continue
      }

      // 解析键值对
      const colonIndex = line.indexOf(':')
      if (colonIndex > -1) {
        const key = line.substring(0, colonIndex).trim()
        const value = line.substring(colonIndex + 1).trim()

        // 处理列表项
        if (value.startsWith('- ')) {
          if (!currentList) {
            currentList = []
            if (currentSection) {
              currentSection[key] = currentList
            }
          }
          currentList.push(value.substring(2).replace(/"/g, ''))
        } else if (currentList) {
          // 列表结束
          currentList = null
        } else if (currentSection) {
          // 处理普通键值对
          currentSection[key] = this._parseValue(value)
        }
      }
    }

    return config
  }

  _parseValue(value) {
    // 移除引号
    value = value.replace(/^["']|["']$/g, '')
    
    // 处理布尔值
    if (value === 'true') return true
    if (value === 'false') return false
    
    // 处理数字
    if (!isNaN(value)) return Number(value)
    
    return value
  }

  get(keyPath, defaultValue = null) {
    const keys = keyPath.split('.')
    let value = this.config

    for (const key of keys) {
      if (value && typeof value === 'object' && key in value) {
        value = value[key]
      } else {
        return defaultValue
      }
    }

    return value
  }

  getServerConfig() {
    return this.config.server || {}
  }

  getCacheConfig() {
    return this.config.cache || {}
  }

  getThrottlingConfig() {
    return this.config.throttling || {}
  }

  getCorsConfig() {
    return this.config.cors || {}
  }

  getUploadConfig() {
    return this.config.upload || {}
  }
}

// 创建全局配置加载器实例
const configLoader = new ConfigLoader()

// 导出配置获取函数
export const getConfig = (keyPath, defaultValue) => {
  return configLoader.get(keyPath, defaultValue)
}

export const getServerConfig = () => configLoader.getServerConfig()
export const getCacheConfig = () => configLoader.getCacheConfig()
export const getThrottlingConfig = () => configLoader.getThrottlingConfig()
export const getCorsConfig = () => configLoader.getCorsConfig()
export const getUploadConfig = () => configLoader.getUploadConfig()

export default configLoader
