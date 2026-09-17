# 航源自动备份

上游：https://hang1888.github.io/

备份越狱源：https://diandianyyy.github.io/archive_hang1888/

GitHub Actions 设置为每 6 小时检查更新（北京时间 02:37、08:37、14:37、20:37）；GitHub 调度可能延迟或跳过。也可以在 Actions 页面手动运行。

只运行一个同步任务，串行下载，请求至少间隔 3 秒。遇到 429 或服务端临时错误时按 Retry-After 和配额重置时间等待重试，最多尝试 5 次。

GitHub 认证优先使用仓库 Secret MY_GITHUB_PAT，未配置时使用 Actions 自带的临时令牌。下载源站文件不携带令牌；GitHub API 的配额与 github.io 下载限流不同。

对比 SHA-256，只下载未备份的安装包，校验大小、哈希和 DEB 格式，随后由 github-actions[bot] 提交并刷新源。上游删除旧版本时保留已经备份的文件。

默认每轮最多下载 100 个包。手动运行时 max_downloads 输入 0 可持续补齐，每 100 个包保存一次进度。

Pages 发布索引；安装包地址指向本备份仓库的固定提交，不依赖上游提供下载。备份范围是上游 Packages 索引中的安装包，不包含上游全部 Git 历史。
