# Prompt to World V2 验收报告

> 验收日期：2026-08-31  
> 验收结论：V2 功能闭环通过；生产级性能与视觉量化门槛仍需在目标设备和正式资产包到位后完成。  
> 对照基线：[V2 产品与技术边界](V2_PRODUCT_AND_TECHNICAL_SPEC.md)

## 1. V1 备份

V1 已在进入 V2 改造前保存为独立源码快照：

- 文件：`backups/v1/prompt-to-world-v1-source-20260831.zip`
- SHA-256：`4ee05d5e030257339beb85cf2ca94845730719a3d66675cb5cedf6039b94e447`
- 校验结果：压缩包可读取，不包含 `.env`、Kimi Key、MySQL 密码、依赖目录、构建产物或缓存。

## 2. 功能范围验收

| 验收项 | 状态 | 结果 |
| --- | --- | --- |
| Prompt 与控制项 | 通过 | 支持风格、质量、时间、天气、密度和 seed；高级选项默认折叠。 |
| 即时 Draft | 通过 | 提交后由确定性编译器立即生成并持久化可探索 Draft。 |
| Kimi Scene Plan | 通过 | Provider 输出严格受 Scene Plan 1.0 Schema 约束，业务层不接收可执行代码。 |
| 渐进 Final | 通过 | Kimi 返回后编译为 Scene JSON 2.0，通过 SSE 无刷新替换 Draft。 |
| 失败降级 | 通过 | Provider 失败、超时或用户停止增强时保留 Draft，并记录 partial 状态。 |
| 五阶段进度 | 通过 | 分析、草稿、风格、资产、完成阶段均持久化并推送。 |
| V2 节点 | 通过 | Procedural、Asset、Prefab、Instances、Decal 均有 Schema、校验与运行时渲染器。 |
| Style Kit | 通过 | 提供赛博东京、温暖低多边形、雾林自然、轨道晨光四套可注册风格。 |
| 局部修改 | 通过 | 环境、风格、密度和按语义移除四类类型化命令可创建新版本。 |
| 版本历史 | 通过 | Draft、Final 和命令结果均为不可变版本，支持查看和恢复。 |
| 场景管理 | 通过 | 支持列表、详情、复制与可恢复的软删除。 |
| 可恢复任务 | 通过 | 任务包含阶段、心跳、租约和恢复入口；本地可内联执行，部署可使用独立 Worker。 |
| V1 兼容 | 通过 | `/api/v1` 保留，提供 Scene JSON 1.0 到 2.0 的迁移器。 |
| 前端按需加载 | 通过 | 3D Runtime 独立为延迟加载 chunk，生成表单可先交互。 |

## 3. 协议与扩展性验收

V2 的扩展边界已经从 Prompt 逻辑中拆开：

```text
LLM Provider -> Scene Plan -> Procedural Compiler -> Scene JSON -> Renderer Registry
                                      │
                                      ├── Style Kit Registry
                                      ├── Asset Catalog
                                      └── Quality Budget
```

- 更换 LLM Provider 不改变 Scene JSON 或渲染器；
- 新增风格通过 Style Kit 目录接入；
- 新增模型通过 Asset Catalog 和 Asset Renderer 接入；
- 新增生成算法通过 Procedural Compiler 注册表接入；
- 前端只渲染白名单节点，不执行 LLM 生成的脚本、URL 或 Three.js 代码；
- Scene Plan 和 Scene JSON 分别验证，避免模型输出直接穿透运行时。

## 4. 自动化验证

| 项目 | 结果 |
| --- | --- |
| 后端测试 | 12 passed |
| 50 条基准 Prompt | 五类场景各 10 条；两次确定性编译结果一致且全部通过 V2 Schema 校验 |
| 前端测试 | 3 passed |
| 前端静态检查 | 通过 |
| 前端生产构建 | 通过 |
| Runtime 拆包 | 通过；Three.js 进入独立延迟加载 chunk |
| 浏览器控制台 | 最终验收窗口内无新增 warning 或 error |
| 响应式检查 | 通过桌面、970 px 中宽和 390 × 844 移动视口检查 |

生产构建中 Three.js 独立 chunk 约 1.07 MB，主入口约 206 KB。体积提示仍存在，但 3D 引擎已不再阻塞主界面首屏加载。

## 5. 真实 Kimi 与渐进生成验收

使用真实 Kimi K3 配置完成一次结构化 V2 生成：

- Draft：分析阶段约 21 ms，草稿阶段约 56 ms，19 个节点；
- Final：总耗时约 10.6 秒；
- Token：约 970 prompt tokens、286 completion tokens；
- Final 场景：33 个节点，赛博东京 Style Kit；
- SSE：确认收到 `job.status`、阶段开始／完成、`draft.ready`、`final.ready` 与失败事件类型。

另一次浏览器端到端生成成功从 Draft 自动升级为 Final，最终显示 36 个节点、3 盏灯和 2 个招牌。停止增强、版本恢复与局部环境命令均在真实页面完成检查。

这些数据证明 V2 已消除 V1 “长时间空等后一次性出现”的主要体验问题，但不是对所有网络条件和提示词的延迟承诺。

### 5.1 月球科研站回归修复

首页提供的月面站点示例曾超出现有五类 archetype 的协议能力，Kimi 只能把它错误归入雾林自然。现已增加 `lunar_station`、`lunar_research_v1`、月球科研舱 Prefab、蓝色陨坑、太阳能阵列、天线与高架平台视点，并为强月球语义增加确定性校正。

使用原始提示词 `A quiet lunar research station above a blue crater at sunrise.` 重新完成真实 Kimi 与浏览器端到端验证。结果为 `蓝坑晨曦站 / 轨道晨光 / sunrise / 16 nodes`，没有树木、植被或鸟居语义；新增两项后端回归测试后，后端测试总数为 14 项。

## 6. 视觉与交互验收

- 保留 V1 深色沉浸式品牌方向，以单一玫红强调色组织操作层级；
- Draft 到 Final 有清晰状态与实际耗时反馈；
- 赛博巷道增加暖／青窗光节奏、环境补光、受控 Bloom 和更可读的暗部；
- 场景工作台可调整环境、风格和密度，并查看／恢复版本；
- 中宽布局将场景读数移到右上，避免覆盖输入面板；
- 移动视口可完整访问输入、生成和场景信息；
- 键盘焦点、对比度和 reduced-motion 规则已覆盖主要控件。

## 7. 已知边界与发布前门槛

以下项目不阻塞 V2 功能验收，但不能被视为已经完成：

1. 当前 Asset Catalog 使用内置几何体和可替换占位资产，没有接入正式 glTF 模型包或 AI 纹理服务；
2. 历史预览是由场景调色板生成的确定性预览块，不是 WebGL 实拍缩略图；
3. Worker 的持久化边界、恢复入口和租约字段已经实现，但尚未做多 Worker 竞争与故障注入压测；当前建议单 Worker；
4. 50 条 Prompt 已完成确定性与 Schema 回归，但尚未逐条生成截图并进行人工盲评分；
5. 尚未在目标集成显卡上完成 P50/P95 FPS、显存和长时间探索测试；
6. Scene JSON 2.0 已表达 LOD 和资产预算边界，当前内置占位渲染器尚不代表最终资产管线的真实下载与解码成本。

生产发布前应补齐目标设备性能基线、50 Prompt 视觉盲测、正式资产许可与压缩策略，以及多 Worker 并发恢复测试。

## 8. 最终结论

V2 已形成完整且可运行的产品闭环：一句 Prompt 会先变成可探索 Draft，再由 Kimi Scene Plan 与确定性编译器升级为视觉更稳定的 Final；用户可以局部修改、恢复历史版本，并在失败时保留已有成果。协议、Provider、编译器、资产、风格、运行时和持久化之间均有独立边界，后续可以在不重写主链路的前提下接入真实模型、AI 纹理、更多程序化生成器和新的 LLM Provider。

因此，本次结论为：**V2 核心功能验收通过，生产发布门槛部分待完成。**
