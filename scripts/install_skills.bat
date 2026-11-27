@echo off
REM Skills 安装脚本 (Windows Batch)
REM 从 gstack 和 hermes-agent 安装 skills

echo ============================================================
echo Skills 安装脚本
echo ============================================================

REM 创建目录结构
echo.
echo 创建目录结构...
mkdir ".claude\skills\01-discovery-and-design" 2>nul
mkdir ".claude\skills\02-architecture-planning" 2>nul
mkdir ".claude\skills\03-development" 2>nul
mkdir ".claude\skills\04-testing-security" 2>nul
mkdir ".claude\skills\05-deployment" 2>nul
mkdir ".claude\skills\06-operations" 2>nul
mkdir ".claude\skills\07-integrations" 2>nul

echo 目录创建完成！

REM ==========================================
REM 01 - 需求发现与设计
REM ==========================================
echo.
echo [01] 安装: 需求发现与设计 Skills...
xcopy /E /I /Y "D:\project\github\gstack\office-hours" ".claude\skills\01-discovery-and-design\office-hours" >nul 2>&1 && echo   ✓ office-hours
xcopy /E /I /Y "D:\project\github\gstack\plan-design-review" ".claude\skills\01-discovery-and-design\plan-design-review" >nul 2>&1 && echo   ✓ plan-design-review
xcopy /E /I /Y "D:\project\github\gstack\design-review" ".claude\skills\01-discovery-and-design\design-review" >nul 2>&1 && echo   ✓ design-review
xcopy /E /I /Y "D:\project\github\gstack\plan-ceo-review" ".claude\skills\01-discovery-and-design\plan-ceo-review" >nul 2>&1 && echo   ✓ plan-ceo-review
xcopy /E /I /Y "D:\project\github\gstack\design-consultation" ".claude\skills\01-discovery-and-design\design-consultation" >nul 2>&1 && echo   ✓ design-consultation
xcopy /E /I /Y "D:\project\github\gstack\design-shotgun" ".claude\skills\01-discovery-and-design\design-shotgun" >nul 2>&1 && echo   ✓ design-shotgun
xcopy /E /I /Y "D:\project\github\gstack\design-html" ".claude\skills\01-discovery-and-design\design-html" >nul 2>&1 && echo   ✓ design-html
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\dogfood\adversarial-ux-test" ".claude\skills\01-discovery-and-design\adversarial-ux-test" >nul 2>&1 && echo   ✓ adversarial-ux-test
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\creative\concept-diagrams" ".claude\skills\01-discovery-and-design\concept-diagrams" >nul 2>&1 && echo   ✓ concept-diagrams

REM ==========================================
REM 02 - 架构与规划
REM ==========================================
echo.
echo [02] 安装: 架构与规划 Skills...
xcopy /E /I /Y "D:\project\github\gstack\spec" ".claude\skills\02-architecture-planning\spec" >nul 2>&1 && echo   ✓ spec
xcopy /E /I /Y "D:\project\github\gstack\plan-eng-review" ".claude\skills\02-architecture-planning\plan-eng-review" >nul 2>&1 && echo   ✓ plan-eng-review
xcopy /E /I /Y "D:\project\github\gstack\plan-devex-review" ".claude\skills\02-architecture-planning\plan-devex-review" >nul 2>&1 && echo   ✓ plan-devex-review
xcopy /E /I /Y "D:\project\github\gstack\context-save" ".claude\skills\02-architecture-planning\context-save" >nul 2>&1 && echo   ✓ context-save
xcopy /E /I /Y "D:\project\github\gstack\context-restore" ".claude\skills\02-architecture-planning\context-restore" >nul 2>&1 && echo   ✓ context-restore
xcopy /E /I /Y "D:\project\github\gstack\autoplan" ".claude\skills\02-architecture-planning\autoplan" >nul 2>&1 && echo   ✓ autoplan

REM ==========================================
REM 03 - 开发与生成
REM ==========================================
echo.
echo [03] 安装: 开发与生成 Skills...
xcopy /E /I /Y "C:\Users\Administrator\.codex\skills\.system\review-agent" ".claude\skills\03-development\review-agent" >nul 2>&1 && echo   ✓ review-agent
xcopy /E /I /Y "C:\Users\Administrator\.codex\skills\.system\skill-creator" ".claude\skills\03-development\skill-creator" >nul 2>&1 && echo   ✓ skill-creator
xcopy /E /I /Y "C:\Users\Administrator\.codex\skills\.system\skill-installer" ".claude\skills\03-development\skill-installer" >nul 2>&1 && echo   ✓ skill-installer
xcopy /E /I /Y "D:\project\github\gstack\careful" ".claude\skills\03-development\careful" >nul 2>&1 && echo   ✓ careful
xcopy /E /I /Y "D:\project\github\gstack\guard" ".claude\skills\03-development\guard" >nul 2>&1 && echo   ✓ guard
xcopy /E /I /Y "D:\project\github\gstack\freeze" ".claude\skills\03-development\freeze" >nul 2>&1 && echo   ✓ freeze
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\devops\docker-management" ".claude\skills\03-development\docker-management" >nul 2>&1 && echo   ✓ docker-management
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\mcp\fastmcp" ".claude\skills\03-development\fastmcp" >nul 2>&1 && echo   ✓ fastmcp
xcopy /E /I /Y "D:\project\github\gstack\codex" ".claude\skills\03-development\codex" >nul 2>&1 && echo   ✓ codex
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\mcp\mcporter" ".claude\skills\03-development\mcporter" >nul 2>&1 && echo   ✓ mcporter
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\web-development\page-agent" ".claude\skills\03-development\page-agent" >nul 2>&1 && echo   ✓ page-agent

REM ==========================================
REM 04 - 测试与安全
REM ==========================================
echo.
echo [04] 安装: 测试与安全 Skills...
xcopy /E /I /Y "D:\project\github\gstack\qa-only" ".claude\skills\04-testing-security\qa-only" >nul 2>&1 && echo   ✓ qa-only
xcopy /E /I /Y "D:\project\github\gstack\qa" ".claude\skills\04-testing-security\qa" >nul 2>&1 && echo   ✓ qa
xcopy /E /I /Y "D:\project\github\gstack\browse" ".claude\skills\04-testing-security\browse" >nul 2>&1 && echo   ✓ browse
xcopy /E /I /Y "D:\project\github\gstack\cso" ".claude\skills\04-testing-security\cso" >nul 2>&1 && echo   ✓ cso
xcopy /E /I /Y "D:\project\github\gstack\review" ".claude\skills\04-testing-security\review" >nul 2>&1 && echo   ✓ review
xcopy /E /I /Y "D:\project\github\gstack\benchmark" ".claude\skills\04-testing-security\benchmark" >nul 2>&1 && echo   ✓ benchmark
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\security\1password" ".claude\skills\04-testing-security\1password" >nul 2>&1 && echo   ✓ 1password
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\security\oss-forensics" ".claude\skills\04-testing-security\oss-forensics" >nul 2>&1 && echo   ✓ oss-forensics

REM ==========================================
REM 05 - 发布与部署
REM ==========================================
echo.
echo [05] 安装: 发布与部署 Skills...
xcopy /E /I /Y "D:\project\github\gstack\ship" ".claude\skills\05-deployment\ship" >nul 2>&1 && echo   ✓ ship
xcopy /E /I /Y "D:\project\github\gstack\setup-deploy" ".claude\skills\05-deployment\setup-deploy" >nul 2>&1 && echo   ✓ setup-deploy
xcopy /E /I /Y "D:\project\github\gstack\land-and-deploy" ".claude\skills\05-deployment\land-and-deploy" >nul 2>&1 && echo   ✓ land-and-deploy
xcopy /E /I /Y "D:\project\github\gstack\canary" ".claude\skills\05-deployment\canary" >nul 2>&1 && echo   ✓ canary
xcopy /E /I /Y "D:\project\github\gstack\document-release" ".claude\skills\05-deployment\document-release" >nul 2>&1 && echo   ✓ document-release
xcopy /E /I /Y "D:\project\github\gstack\landing-report" ".claude\skills\05-deployment\landing-report" >nul 2>&1 && echo   ✓ landing-report

REM ==========================================
REM 06 - 运维与维护
REM ==========================================
echo.
echo [06] 安装: 运维与维护 Skills...
xcopy /E /I /Y "D:\project\github\gstack\investigate" ".claude\skills\06-operations\investigate" >nul 2>&1 && echo   ✓ investigate
xcopy /E /I /Y "D:\project\github\gstack\health" ".claude\skills\06-operations\health" >nul 2>&1 && echo   ✓ health
xcopy /E /I /Y "D:\project\github\gstack\document-generate" ".claude\skills\06-operations\document-generate" >nul 2>&1 && echo   ✓ document-generate
xcopy /E /I /Y "D:\project\github\gstack\retro" ".claude\skills\06-operations\retro" >nul 2>&1 && echo   ✓ retro
xcopy /E /I /Y "D:\project\github\gstack\learn" ".claude\skills\06-operations\learn" >nul 2>&1 && echo   ✓ learn

REM ==========================================
REM 07 - AI媒体与集成
REM ==========================================
echo.
echo [07] 安装: AI媒体与集成 Skills...
xcopy /E /I /Y "C:\Users\Administrator\.codex\skills\.system\imagegen" ".claude\skills\07-integrations\imagegen" >nul 2>&1 && echo   ✓ imagegen
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\mlops\whisper" ".claude\skills\07-integrations\whisper" >nul 2>&1 && echo   ✓ whisper
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\devops\cli" ".claude\skills\07-integrations\inference-sh-cli" >nul 2>&1 && echo   ✓ inference-sh-cli
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\research\duckduckgo-search" ".claude\skills\07-integrations\duckduckgo-search" >nul 2>&1 && echo   ✓ duckduckgo-search
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\mlops\stable-diffusion" ".claude\skills\07-integrations\stable-diffusion" >nul 2>&1 && echo   ✓ stable-diffusion
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\research\parallel-cli" ".claude\skills\07-integrations\parallel-cli" >nul 2>&1 && echo   ✓ parallel-cli
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\research\qmd" ".claude\skills\07-integrations\qmd" >nul 2>&1 && echo   ✓ qmd
xcopy /E /I /Y "D:\project\github\hermes-agent\optional-skills\research\scrapling" ".claude\skills\07-integrations\scrapling" >nul 2>&1 && echo   ✓ scrapling

echo.
echo ============================================================
echo 安装完成！
echo ============================================================
echo.
echo Skills 已安装到: .claude\skills\
echo.
echo 目录结构:
dir /B ".claude\skills"
echo.
pause