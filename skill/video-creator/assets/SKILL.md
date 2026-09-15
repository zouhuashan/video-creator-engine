# Asset Router 阶段

读取 [asset-routing.json](../../../config/asset-routing.json) 后，为每个分镜选择第一个可用路由：真实素材、授权素材、HyperFrames、生成式媒体。不得因方便跳过更高优先级的可用素材。

使用 `scripts.asset_router.choose_route` 选择路由；没有可用候选时返回 `MISSING_ASSET`。随后调用 `recover_missing_asset`，严格按搜索、生成、替换为信息图、请求用户材料的顺序选择第一个可用恢复动作。没有自动动作可用时请求用户材料并保留任务，不把项目标记为失败。

素材文件准备好后，按 [asset-manifest-input.schema.json](../../../templates/asset-manifest-input.schema.json) 填写来源与授权，运行 `./video-creator assets <project-id> --input-file <JSON>`。命令只接受项目目录内已存在的文件，计算 SHA-256 校验和并写入 `asset-manifest.json`；生成素材必须记录 provider。
