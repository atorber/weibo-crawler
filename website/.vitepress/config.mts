import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: 'Weibo Crawler',
  description: '高效、稳定、开箱即用的新浪微博采集、发布与数据管理平台',
  base: '/weibo-crawler/',
  vite: {
    server: {
      port: 15000,
      host: '0.0.0.0'
    }
  },
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/weibo-crawler/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#e6162d' }]
  ],
  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: '首页', link: '/' },
      { text: '使用指南', link: '/guide/intro' },
      { text: '🔌 透传网关', link: '/guide/passthrough' },
      { text: '配置参数', link: '/guide/config' },
      { text: '数据存储', link: '/guide/database' },
      { text: 'API 服务', link: '/api/' },
      {
        text: '更多',
        items: [
          { text: '🔌 Weibo 原生透传网关', link: '/guide/passthrough' },
          { text: '✍️ 发布与博文管理', link: '/guide/publish' },
          { text: '🤖 Agent 技能', link: '/guide/agent-skill' },
          { text: '获取 User ID', link: '/guide/user-id' },
          { text: 'Cookie 指南', link: '/guide/cookie' },
          { text: '自动化爬取', link: '/guide/automation' },
          { text: 'Docker 部署', link: '/guide/docker' }
        ]
      }
    ],

    sidebar: {
      '/guide/': [
        {
          text: '架构与起步',
          items: [
            { text: '项目简介（双层架构）', link: '/guide/intro' },
            { text: '快速开始', link: '/guide/quick-start' }
          ]
        },
        {
          text: '层面一：透传网关与客户端底座',
          items: [
            { text: '🔌 Weibo 原生透传网关与客户端开发', link: '/guide/passthrough' },
            { text: '✍️ 微博发布与博文管理', link: '/guide/publish' }
          ]
        },
        {
          text: '层面二：爬虫任务与存档查询',
          items: [
            { text: '输出内容与格式', link: '/guide/output' },
            { text: '完整配置参数', link: '/guide/config' },
            { text: '如何获取 User ID', link: '/guide/user-id' },
            { text: 'Cookie 获取与验证', link: '/guide/cookie' },
            { text: '数据库配置 (MySQL/MongoDB/SQLite)', link: '/guide/database' },
            { text: '定期自动增量爬取', link: '/guide/automation' },
            { text: 'Docker 容器化部署', link: '/guide/docker' },
            { text: '二次开发与 Python 调用', link: '/guide/advanced' }
          ]
        },
        {
          text: 'AI Agent 集成',
          items: [
            { text: '🤖 Agent 技能 (weibo-viewer)', link: '/guide/agent-skill' }
          ]
        }
      ],
      '/api/': [
        {
          text: 'RESTful API',
          items: [
            { text: 'API 概述与启动', link: '/api/' },
            { text: '接口端点与调用示例', link: '/api/endpoints' }
          ]
        }
      ]
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/atorber/weibo-crawler' }
    ],

    search: {
      provider: 'local',
      options: {
        locales: {
          root: {
            translations: {
              button: {
                buttonText: '搜索文档',
                buttonAriaLabel: '搜索文档'
              },
              modal: {
                noResultsText: '无法找到相关结果',
                resetButtonTitle: '清除查询条件',
                footer: {
                  selectText: '选择',
                  navigateText: '切换',
                  closeText: '关闭'
                }
              }
            }
          }
        }
      }
    },

    footer: {
      message: '基于 Apache-2.0 协议开源',
      copyright: 'Copyright © 2020-present Weibo Crawler Contributors'
    },

    docFooter: {
      prev: '上一篇',
      next: '下一篇'
    },

    outline: {
      label: '页面导航',
      level: [2, 3]
    },

    lastUpdated: {
      text: '最后更新于'
    }
  }
})
