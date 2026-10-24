"""兼容启动器：供 run_bot.bat 双击与 Windows 任务计划程序调用。

用「文件路径」方式运行时 Python 会自动把本文件所在目录加入 sys.path，
因此无论工作目录在哪都能找到 arxiv_bot 包。
"""
from arxiv_bot.cli import main

if __name__ == "__main__":
    main()
