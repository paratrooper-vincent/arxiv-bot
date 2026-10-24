@echo off
rem arxiv-bot launcher: double-click me, or let Task Scheduler call me
rem Full python path so it works without PATH configuration
cd /d "%~dp0"
D:\Miniconda\python.exe run_bot.py run
