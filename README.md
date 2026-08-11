# 🌸 localPartner
搭配kazumi食用的本地视频播放服务。

> 这并不是最简洁的解决方案。b站有一起看功能，资源丰富，服务稳定。如果想做到更可控的本地视频播放，同时实现复杂的画质改善、外挂字幕、一起看等功能，考虑使用mpv+滤镜+Syncplay。弹弹play同样是成熟且友好的弹幕本地播放器。另外本工具暂时没办法播放外挂字幕视频，若确有需求，考虑上述其他工具或者把外挂字幕硬嵌入视频。
## 功能简要介绍
1.搜索用户指定的目录，检索出需要播放的番剧视频，通过解析文件名获取基本信息。

2.连接萌娘百科/Bangumi API，检索出番剧的通用名。（可选）

3.根据kazumi规则文档指示，在指定端口上部署http服务，充当临时的“API”，供Kazumi当作视频源连接。

4.在kazumi上妥当配置规则后，搜索对应的番剧并选择软件对应的规则源播放，Kazumi会连接到localPartner的服务并直接播放本地视频，基本实现秒加载。

## 使用方法

**[B站图文教程](https://www.bilibili.com/opus/1235382467239608324)**

1.指定一个或多个搜索目录，选择联网检索源，并点击开始扫描。软件会检索出目录下的视频，根据文件名读取番剧名，并尝试以此通过在线检索源获取番剧标准名称。检索源选择无则会直接跳过在线检索，使用文件名读取出的番剧名。

2.指定一个空闲的端口，点击启动服务。

3.确定服务正常启动后，前往kazumi->我的->设置->规则管理->新建规则，根据软件里“Kazumi API 指南”页面的配置信息配置好规则。

> 如果你就在本地运行服务，且采用默认端口8080，那可以直接复制下列链接到kazumi里，从剪贴板导入规则，一键完成配置。
```link
kazumi://eyJhcGkiOiI4IiwidHlwZSI6ImFuaW1lIiwibmFtZSI6ImxvY2FsUGFydG5lciIsInZlcnNpb24iOiIxIiwibXVsaVNvdXJjZXMiOnRydWUsInVzZVdlYnZpZXciOnRydWUsInVzZU5hdGl2ZVBsYXllciI6dHJ1ZSwidXNlUG9zdCI6ZmFsc2UsInVzZUxlZ2FjeVBhcnNlciI6ZmFsc2UsImFkQmxvY2tlciI6ZmFsc2UsInVzZXJBZ2VudCI6IiIsImJhc2VVUkwiOiJodHRwOi8vbG9jYWxob3N0OjgwODAiLCJzZWFyY2hVUkwiOiIiLCJzZWFyY2hMaXN0IjoiIiwic2VhcmNoTmFtZSI6IiIsInNlYXJjaFJlc3VsdCI6IiIsImNoYXB0ZXJSb2FkcyI6IiIsImNoYXB0ZXJSZXN1bHQiOiIiLCJyZWZlcmVyIjoiIiwic2VhcmNoTW9kZSI6ImFwaSIsImNoYXB0ZXJNb2RlIjoiYXBpIiwic2VhcmNoQXBpQ29uZmlnIjp7InJlcXVlc3QiOnsibWV0aG9kIjoiR0VUIiwidXJsIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2FwaS9zZWFyY2giLCJxdWVyeSI6eyJxIjoiQGtleXdvcmQifX0sImxpc3RQYXRoIjoiJC5kYXRhWypdIiwibmFtZVBhdGgiOiIkLm5hbWUiLCJzb3VyY2VQYXRoIjoiJC5pZCJ9LCJjaGFwdGVyQXBpQ29uZmlnIjp7InJlcXVlc3QiOnsibWV0aG9kIjoiR0VUIiwidXJsIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2FwaS9kZXRhaWwvQHNvdXJjZSJ9LCJmb3JtYXQiOiJuZXN0ZWQiLCJyb2Fkc1BhdGgiOiIkLmRhdGEucGxheVNvdXJjZXNbKl0iLCJyb2FkTmFtZVBhdGgiOiIkLm5hbWUiLCJlcGlzb2Rlc1BhdGgiOiIkLmVwaXNvZGVzWypdIiwiZXBpc29kZU5hbWVQYXRoIjoiJC5uYW1lIiwiZXBpc29kZVVybFBhdGgiOiIkLnVybCJ9LCJhbnRpQ3Jhd2xlckNvbmZpZyI6eyJlbmFibGVkIjpmYWxzZSwiY2FwdGNoYVR5cGUiOjEsImNhcHRjaGFJbWFnZSI6IiIsImNhcHRjaGFJbnB1dCI6IiIsImNhcHRjaGFCdXR0b24iOiIiLCJjYXB0Y2hhRGV0ZWN0VHlwZSI6MSwiY2FwdGNoYURldGVjdFZhbHVlIjoiIiwiY2FwdGNoYVNjcmlwdCI6IiJ9fQ==
``` 

4.在kazumi搜索要看的番剧，找到第3步新建的源，点击播放即可。软件会根据读取的视频文件确定集数和集号并对应提供给kazumi，不受在线识别影响。

## FAQ
Q：番剧名识别/在线检索出错？

A：只要同一部作品被正确归到一起（这个条件是在同一文件夹下有且仅有一部作品）且集数识别正常就不影响观看，在kazumi里手动检索它被错误识别的名字即可。另外，对于不确定是否规范或者总是无法准确归类的番剧文件，让ai写一个批量脚本重命名成类似下列格式：
番剧名 [01].mkv，并放在同一个文件夹里，且确保这个文件夹下只有需要的视频文件，能大大提高识别成功率。

Q：指定目录下的文件没被扫到？

A：支持的视频格式：.mkv/.mp4/.avi/.flv/.mov/.webm/.ts/.m4v。另外，程序只会搜索指定目录当层和下一层的文件，不会深入到第三层及以后，以防扫描到CDs/SPs等杂项文件，同时加快速度。以下是文件结构示例：

- localPartner.exe（或指定目录）
- 番剧A
  - CDs [不会被扫描！]
    - xxx.wav
    - ... 
  - 番剧A [01].mkv
  - 番剧A [02].mkv
  - ...
- 番剧B
  - 番剧B [01].mkv
  - ...

## 技术细节
项目基于Python+pyinstaller打包。

后端实质为一个媒体流Http服务端，具体细节：
- 以文件夹区分各作品，anitopy解析文件名，辅之以在线请求api，失败时自动回退
- 在线请求时，当检索源不变，则为一部作品赋予一致的id（从源获取），供kazumi识别
- 多线程处理播放请求
- ipv4/v6双栈监听
- http断点续传与媒体分段流式分发

前端采用wxPython制作。

本程序采用AI编程+人工指导修缮的方式完成。
## 致谢和声明
本程序的开发离不开优秀项目、API等：
* **[Kazumi](https://github.com/Predidit/kazumi)**：优秀的番剧播放器。
* **[Anitopy](https://github.com/igorcmoura/anitopy)**：高效的动画文件名解析库。
* **[Bangumi.tv](https://bgm.tv/)** & **[萌娘百科](https://zh.moegirl.org.cn/)**：提供动画条目与元数据检索服务。
* **Gemini 3.6 Flash**：写代码还真不错，基本一遍跑通，就是上下文太短了点。

另外，
* 本工具仅供个人本地媒体管理和播放，不提供、不存储、不传播任何盗版影视资源。用户自行配置或使用本工具产生的任何版权问题，由使用者自行承担。
* 若使用者将本服务端口（IPv4/IPv6）暴露于公网，请自行评估并承担潜在的网络安全风险。
* 作者水平有限，如有可改善之处，烦请指出，不胜感谢。除重大bug等情况外，本程序已经实现目标功能，默认不再更新。
