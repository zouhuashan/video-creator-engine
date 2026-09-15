# Asset Router 阶段

读取 [asset-routing.json](../../../config/asset-routing.json) 后，为每个分镜选择第一个可用路由：真实素材、授权素材、HyperFrames、生成式媒体。不得因方便跳过更高优先级的可用素材。

使用 `scripts.asset_router.choose_route` 选择路由；没有可用候选时返回 `MISSING_ASSET`，后续按缺失素材流程处理。素材清单和实际获取由后续任务写入，不在此阶段伪造素材文件或授权信息。
