# 项目介绍

本项目作为Alear030的第一个AGENT项目存在

# 项目结构

## core(read_only)

 - agent_class
 - agent_loop


## memory

大体分为  

 - 基础记忆(read-only)：system_soul、Agents……
 - 长期记忆：USER
 - 短期记忆：sessions
 - 特殊记忆：

## tool

大体分为三类  

 - 辅助类：工具注册器、工具匹配器…
 - 基础工具(read-only)：文件读写、命令执行、计划制定、意图识别、多智能体、技能创建、会话总结、记忆压缩、记忆查询…
 - 通用工具：web_search、web_fetch…

## skill

大体分为

 - 基础skills(read-only)
 - 自创建skills
 - 外部skills

## 配置(read_only)

 - config.yaml
 - .env