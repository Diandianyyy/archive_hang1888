# 航源自动备份

上游：https://hang1888.github.io/

备份越狱源：https://diandianyyy.github.io/archive_hang1888/

GitHub Actions 设置为每小时第 37 分钟检查更新；GitHub 调度可能延迟或跳过，不能保证准点运行。也可以在 Actions 页面手动运行。

对比 SHA-256，只下载未备份的安装包，校验大小、哈希和 DEB 格式，随后由 github-actions[bot] 提交并刷新源。上游删除旧版本时保留已经备份的文件。

默认每轮最多下载 100 个包。手动运行时 max_downloads 输入 0 可持续补齐，每 100 个包保存一次进度。

Pages 发布索引；安装包地址指向本备份仓库的固定提交，不依赖上游提供下载。备份范围是上游 Packages 索引中的安装包，不包含上游全部 Git 历史。
