# Prompt to World V2 产品与技术边界

> 实施状态：V2 核心功能已于 2026-08-31 完成，结果与未关闭的生产发布门槛见 [V2 验收报告](V2_ACCEPTANCE_REPORT.md)  
> 文档状态：V2 产品与技术基线  
> 基线来源：V1 源码快照、V1 需求边界、V1 验收报告与真实 Kimi K3 时延数据  
> V2 主题：更快看到世界、更容易控制结果、更稳定地产生高质量画面

## 0. 执行摘要

V1 已证明 `Prompt → Kimi → Scene JSON → React Three Fiber → 3D World` 的功能闭环成立，但也暴露了两个根本问题：

1. LLM 直接枚举完整 Primitive 场景，输出通常需要数千 tokens，真实生成约 75～93 秒，且结果越丰富延迟越高；
2. 视觉质量主要依赖 LLM 对坐标、材质和灯光的逐项发挥，缺少稳定的构图规则、资产语言、风格系统和质量预算。

V2 不应继续让 LLM 输出越来越大的低层 Scene JSON。核心改动是引入一个紧凑的 `Scene Plan`：LLM 负责理解意图、空间关系、视觉风格和关键物件；确定性 `Procedural Compiler` 负责把计划展开为可渲染的 Scene JSON 2.0。系统先生成可探索的 Blockout，再渐进完成材质、资产、灯光和细节。

```text
Prompt + Controls
        │
        ▼
Intent / Scene Plan 1.0        小而严格的 LLM 输出
        │
        ▼
Procedural Compiler            确定性布局、风格套件、预算控制
        │
        ├──────────────► Draft Scene JSON 2.0 ──► 立即预览
        │
        ▼
Asset + Material Resolver      白名单资产、PBR 材质、LOD
        │
        ▼
Final Scene JSON 2.0           不可变版本
        │
        ▼
Scene Runtime 2.0              探索、查看、局部编辑
```

V2 仍然是 AI Scene Engine，不变成 AI 写 Three.js 代码的工具；Scene JSON 仍是运行时边界，但 LLM 不再负责逐节点完成所有底层细节。

## 1. V2 产品目标

### 1.1 必须实现的用户价值

1. 用户提交描述后，先看到可用的空间草稿，而不是面对一分钟以上的静态等待；
2. 最终场景在构图、材质、光照、重复细节和主题一致性上明显优于 V1；
3. 用户能锁定喜欢的部分，只重做风格、灯光、密度或某个区域；
4. 失败、刷新或后端重启不会让已经完成的有效阶段消失；
5. 相同 Prompt、控制项、编译器版本与 seed 能得到可重复结果；
6. 新增风格、资产包、程序化生成器和 LLM Provider 时，不重写主链路。

### 1.2 V2 不追求的目标

- 不追求照片级写实、电影级全局光照或大型开放世界；
- 不让 Kimi 生成 React、Three.js、Shader、脚本或任意可执行内容；
- 不直接生成真正 AI Mesh；
- 不进入 NPC、完整物理、多人协作和 Minecraft 式体素世界；
- 不建设完整 Blender 替代品或通用 Level Editor；
- 不以堆叠更多后处理掩盖构图、材质和资产质量问题。

## 2. V1 到 V2 的关键变化

| 维度 | V1 | V2 |
| --- | --- | --- |
| LLM 输出 | 完整 Primitive Scene JSON | 紧凑 Scene Plan，可选受控 Scene Commands |
| 场景构建 | LLM 逐节点给坐标 | 程序化编译器按规则展开布局与细节 |
| 生成反馈 | 等待完整结果后载入 | 阶段事件、Blockout 预览、渐进替换 |
| 视觉语言 | 单节点颜色与 Emissive | Style Kit、PBR Material Set、Prefab、Decal、Lighting Rig |
| 节点能力 | Primitive、Text、Light、Group | 增加 Procedural、Asset、Prefab、Instances、Decal |
| 修改方式 | 整体重新生成 | 类型化局部命令生成新版本 |
| 历史 | 场景列表与不可变版本 | 缩略图、版本时间线、变更摘要、恢复与派生 |
| 任务执行 | 进程内异步任务 | 可恢复阶段、持久任务租约、独立 Worker 边界 |
| 质量控制 | Schema 与全局数量上限 | 质量档位、资产预算、LOD、风格规则、视觉评分 |
| 观测 | 任务耗时与错误 | 分阶段耗时、首个草稿时间、资产命中率、FPS 与质量指标 |

## 3. 核心用户路径

### 3.1 首次生成

1. 用户输入自然语言描述；
2. 可选选择风格、时间、天气、密度、质量档和 seed；
3. 系统在 300 ms 内确认任务，并展示明确阶段与已用时间；
4. Scene Plan 完成后生成可探索 Blockout，用户无需等待最终细节；
5. 材质、资产、灯光和环境细节渐进加载；
6. 最终版本通过验证后自动成为当前版本；
7. 用户可以探索、查看版本信息、保存 seed 或继续修改。

### 3.2 受控修改

用户可以发出“让雨更大”“把灯光改成暖色”“增加街边杂物”“保留布局换成复古日本风”等请求。系统必须先把请求编译成白名单 `Scene Command`，再基于当前不可变版本创建新版本。

V2 首批允许的命令：

- `set_environment`：时间、天空、雾、天气、曝光；
- `set_style_kit`：替换整体视觉套件，但保留布局；
- `set_density`：调整可重复细节密度；
- `regenerate_region`：只重建一个命名区域；
- `add_cluster`：添加受控类型的物件簇；
- `remove_by_semantics`：按语义标签移除物件；
- `set_material_ref`：替换指定语义对象的材质集；
- `move_anchor`：移动关键锚点，重新求解相邻布局。

禁止把自然语言直接转换为任意 JSON Patch，也禁止让前端跳过服务端校验直接修改 Scene JSON。

### 3.3 失败恢复

- Scene Plan 失败：保留输入与控制项，提供立即重试；
- 最终增强失败：保留已经可探索的 Blockout，不把整个任务显示为不可用；
- 页面刷新：根据 `jobId` 恢复当前阶段和最近有效场景；
- Worker 重启：从最后阶段检查点继续，或明确标记可重试；
- 资产加载失败：使用 Primitive/Material Fallback，不影响其余场景。

## 4. V2 生成架构

### 4.1 分阶段管线

#### Stage A：输入规范化

- 清理 Prompt，提取语言，不改写用户意图；
- 合并 UI 控制项与默认质量档；
- 生成稳定的请求指纹，用于幂等和缓存；
- 检查成本、长度、速率和敏感配置边界。

#### Stage B：Scene Plan

Kimi 只输出约 0.5～2 KB 的严格 JSON，内容包括：

- 世界类型和一句话视觉方向；
- 区域与邻接关系；
- 可行走主路径；
- 关键锚点及其语义；
- 风格、色板、时间、天气和材质倾向；
- 密度、尺度、镜头和必须出现/禁止出现的元素；
- 程序化生成器参数，不含大量底层节点。

示例：

```json
{
  "planVersion": "1.0.0",
  "title": "Neon Ramen Alley",
  "seed": 184726,
  "archetype": "urban_alley",
  "styleKit": "cyberpunk_tokyo_v1",
  "mood": {
    "time": "night",
    "weather": "light_rain",
    "palette": ["#ff3f78", "#22d3ee", "#080a12"]
  },
  "layout": {
    "path": "narrow_linear",
    "width": 5,
    "length": 28,
    "density": 0.72
  },
  "anchors": [
    {"role": "ramen_shop", "side": "left", "importance": "hero"},
    {"role": "izakaya", "side": "right", "importance": "support"}
  ],
  "mustInclude": ["readable_ramen_sign", "wet_road", "street_lights"],
  "avoid": ["cars", "daylight"]
}
```

Scene Plan 是 LLM 契约，不是 Renderer 契约。前端运行时不得直接解释 Scene Plan。

#### Stage C：Procedural Blockout

- 根据 archetype 选择编译策略；
- 生成道路、边界、建筑体量、路径、相机、碰撞和基础灯光；
- 在后端完成空间约束求解，避免相机出生在碰撞体内；
- 输出通过校验的 Draft Scene JSON 2.0；
- 保存阶段检查点并通过 SSE 通知前端加载。

#### Stage D：视觉增强

- 根据 Style Kit 替换材质、立面部件、招牌、道具和灯光 Rig；
- Asset Resolver 只从白名单 Catalog 选择资产；
- 重复元素转为实例化节点；
- 根据质量档计算 LOD、阴影、纹理和后处理预算；
- 生成最终 Scene JSON 2.0，不直接修改已保存 Draft 版本。

#### Stage E：最终验证与缩略图

- 执行 Schema、语义、空间、资产、安全和性能预算验证；
- 创建不可变 Final Version；
- 生成固定镜头缩略图；
- 记录阶段耗时、tokens、资产命中和降级信息。

### 4.2 Provider 路由边界

Provider 继续通过接口隔离：

```text
compile_plan(prompt, preferences, plan_schema) -> PlanResult
compile_command(scene_summary, instruction, command_schema) -> CommandResult
```

- 模型名通过配置别名 `fast`、`balanced`、`quality` 解析，不进入领域代码；
- V2 默认仍可只使用 Kimi K3；未来增加更快模型时不修改业务层；
- Provider 不知道 MySQL、Three.js、资产 URL 或场景版本表；
- 流式 token 只用于进度与诊断，未完成 JSON 不进入 Renderer；
- 自动修复只允许一次 LLM 修复，优先使用本地 Normalizer 和确定性规则。

## 5. Scene JSON 2.0

### 5.1 兼容策略

- V1 `1.0.0` 文档永久可读；
- 新增独立 `1.x → 2.0` Migrator，不原地覆盖历史 JSON；
- V2 Runtime 接受 1.0 和 2.0，内部统一为 Runtime Scene；
- V2 新场景只写 2.0；
- 主版本变化必须有 Schema、迁移夹具、前后兼容测试和回滚路径。

### 5.2 新节点

#### `procedural`

首批白名单 subtype：

- `building_row`；
- `shop_facade`；
- `road_segment`；
- `prop_scatter`；
- `vegetation_cluster`；
- `cable_network`；
- `sign_cluster`。

每个 subtype 都必须有固定参数 Schema、seed、预算估算、Fallback 和测试。LLM 不能发明新的 generator 名称。

#### `asset`

- 只保存 `assetRef`、variant、transform、LOD 与语义；
- `assetRef` 只能来自服务端 Asset Catalog；
- LLM 只能请求资产类别和语义，Asset Resolver 决定真实 Catalog ID；
- 禁止任意 URL、Data URI、Base64 模型和用户提供的脚本资产。

#### `prefab` 与 `instances`

- Prefab 表达可复用组合，例如灯柱加灯头、店面加招牌；
- Instances 表达同材质、同几何的批量实例；
- Runtime 优先使用 `InstancedMesh`，并统计实例总量而非只统计节点数。

#### `decal`

- 用于污渍、路面标记、海报和局部发光细节；
- V2 只接受 Catalog 中的纹理引用；
- 严格限制透明层数和覆盖面积，避免 overdraw 失控。

### 5.3 Style Kit

Style Kit 是版本化配置资产，不由 LLM 临时创造。每个套件包含：

- 色板与对比度规则；
- PBR Material Set；
- 建筑立面与 Prefab 选择权重；
- 招牌字体、Decal 和道具词汇；
- Lighting Rig；
- 雾、天空、曝光和后处理上限；
- 不同质量档的降级规则。

V2 首发至少提供三个有明显区分度的套件：

1. `cyberpunk_tokyo_v1`：湿地面、霓虹、密集招牌、冷暖对比；
2. `cozy_lowpoly_v1`：低多边形、暖色、柔和阴影、低后处理；
3. `misty_nature_v1`：岩石、植被簇、雾层和自然色温。

风格质量来自经过测试的套件与生成规则，不来自在 Prompt 中堆叠“cinematic、4K、ultra detailed”等词。

## 6. 视觉质量升级

### 6.1 构图

- 每个场景必须有主路径、视觉焦点、前中后景和至少一个遮挡揭示关系；
- Hero Anchor 不得被普通道具遮挡；
- 相机出生点必须能看到主焦点或明确引导方向；
- 建筑与自然环境使用不同布局求解器，不共享随机散点逻辑；
- 生成器对间距、尺度、对齐、穿插和可通行宽度执行几何约束。

### 6.2 材质与纹理

- 支持 Catalog PBR 纹理集：base color、normal、roughness、metalness、AO；
- 支持受控 UV scale、rotation、tint 和 wetness；
- 重复建筑优先使用纹理 Atlas 和材质复用；
- 所有纹理提供尺寸、颜色空间、压缩格式和显存预算元数据；
- V2 必须项只使用策展纹理库；AI 纹理生成仅保留 Provider 接口，不作为发布依赖。

### 6.3 灯光与环境

- 使用 Lighting Rig，而不是让 LLM 随机放置大量 Point Light；
- 默认由环境光/天空、主光、填充光和少量强调光构成；
- 投射阴影灯光最多 2 个，低质量档最多 1 个；
- 霓虹优先依靠 Emissive、Bloom 和局部补光，不为每个招牌建立真实光源；
- 湿地面使用粗糙度、环境反射与局部高光模拟，不把昂贵 SSR 作为 V2 必须项；
- 支持雨、薄雾、浮尘等轻量粒子效果，不模拟真实流体。

### 6.4 资产与重复细节

- 首批资产聚焦高复用类别：门窗、空调外机、管道、路灯、招牌、箱子、垃圾袋、植被、岩石；
- 每个资产必须有包围盒、碰撞简化体、LOD、三角形数、材质数和许可证元数据；
- 同类细节通过 seed 与密度展开，避免完全相同的复制排列；
- 资产不可用时退化为 Prefab 或 Primitive，不中断整个场景。

### 6.5 质量档

| 档位 | 目标 | 主要策略 |
| --- | --- | --- |
| Draft | 最快可探索 | Primitive、基础材质、无阴影或单阴影、关闭 Bloom |
| Balanced | 默认体验 | PBR、有限资产、1～2 个阴影灯、适度 Bloom、LOD |
| Quality | 截图与高性能设备 | 更高纹理档、更多 Decal/Props、更远 LOD、受控后处理 |

质量档影响 Renderer 和编译预算，不改变用户场景语义。

## 7. 用户体验设计要求

### 7.1 生成界面

- Prompt 为主输入，高级控制默认收起；
- 风格、时间、天气、密度和质量档使用可见控件，不要求用户学习 Prompt 技巧；
- 显示“分析意图、构建草稿、应用风格、加载资产、完成”五阶段；
- 显示真实已用时间，不展示虚假百分比；
- Blockout 完成后允许立即探索，增强阶段在后台继续；
- 用户取消增强时保留最后一个有效 Draft；
- 失败提示必须包含“发生了什么、保留了什么、下一步能做什么”。

### 7.2 场景工作区

- 默认保持 3D 世界为主视觉；
- 支持 Explore 和 Inspect 两种模式，避免指针锁定与页面操作冲突；
- Inspect 模式提供对象悬停语义、性能摘要和版本信息，不做完整自由编辑器；
- 清晰显示当前版本是 Draft 还是 Final；
- 提供相机重置、截图、复制链接到本地场景、查看 Scene JSON 等低频工具。

### 7.3 历史与版本

- 历史卡片显示缩略图、Prompt 摘要、风格、版本状态、耗时和节点预算；
- 场景详情展示不可变版本时间线；
- 支持从旧版本“恢复为新版本”，禁止覆盖旧版本；
- 支持复制/派生场景；
- 删除能力进入 V2，但必须二次确认并定义匿名数据保留策略；
- V2 不提供多人合并、分支冲突解决或公共社区 Feed。

### 7.4 可访问性和设备边界

- 桌面 Chrome/Edge 仍是创作主目标；
- 窄屏提供查看、历史和基础生成，不承诺完整第一人称操作；
- 键盘、焦点、对比度、Reduced Motion 与无 Pointer Lock 降级必须测试；
- WebGL2 不可用时展示能力说明和静态缩略图，不出现空白页。

## 8. 前端技术改动

- 将生成任务状态从页面组件抽为独立 server-state 模块；
- 使用 SSE 接收阶段事件，轮询作为降级路径；
- Scene Runtime 2.0 增加 `ProceduralRegistry`、`AssetRegistry`、`MaterialRegistry`；
- 将大型 Three.js/Postprocessing 模块按路线动态加载；
- 引入资源预加载、引用计数和离场释放，避免切换历史后显存泄漏；
- 对重复节点使用 Instancing，对资产使用 LOD；
- 建立统一 Quality Profile，根据设备能力和用户选择计算 DPR、阴影、纹理和后处理；
- 增加开发模式 FPS、draw calls、triangles、textures 和 GPU memory 估算面板；
- 每种新节点都必须有 Node Error Boundary 与视觉 Fallback。

前端不得：

- 直接调用 LLM；
- 根据语义字符串临时猜测任意模型 URL；
- 在浏览器执行 Scene JSON 中的代码；
- 把未验证的流式 JSON 片段送入 Runtime；
- 让 UI 状态成为场景版本的唯一事实来源。

## 9. 后端技术改动

### 9.1 新模块

```text
backend/app/
  domain/
    scene_plan/
    scene_v2/
    scene_commands/
    budgets/
  compilers/
    plan_compiler/
    procedural_compiler/
    style_compiler/
  assets/
    catalog/
    resolver/
  jobs/
    worker/
    stage_runner/
    event_stream/
  migrations/
    scene_1_to_2/
```

### 9.2 持久任务

V2 必须把任务阶段和检查点持久化，避免 FastAPI 进程重启后任务永久丢失。

- MySQL 继续保存任务事实状态；
- 初始实现可使用 MySQL 租约加独立 Worker，不强制新增 Redis；
- Worker 使用租约、心跳和幂等阶段，支持崩溃回收；
- 当并发量证明需要时，再在同一接口后切换 Redis/Celery、RQ 或其他队列；
- Web API 不直接持有长时间生成协程的唯一所有权。

### 9.3 编译缓存

缓存键至少包含：

- 规范化 Prompt 哈希；
- preferences；
- Scene Plan Schema 版本；
- Prompt 模板版本；
- Provider/model 别名；
- Procedural Compiler 版本；
- Style Kit 版本；
- seed。

缓存只复用通过验证的 Plan 或 Scene Version。失败响应、未经验证输出和跨用户私有数据不得直接共享。

## 10. 数据模型变更

### 新表

#### `generation_stages`

- `job_id`、阶段名、状态、attempt、开始/完成时间、错误码；
- 安全的 token/耗时元数据；
- Draft/Final checkpoint version 引用。

#### `scene_commands`

- 来源版本、类型化命令 JSON、用户原始指令、结果版本、状态和审计元数据；

#### `asset_catalog`

- 稳定 asset ID、类别、版本、URI、许可证、包围盒、LOD、三角形数、材质数和状态；

#### `style_kits`

- 稳定名称、版本、配置 JSON、兼容的 Runtime/Schema 版本和启用状态。

### 现有表扩展

- `scene_versions`：增加 `parent_version_id`、`version_kind`、`change_summary`、`plan_json`、`compiler_version`、`style_kit_version`、`quality_profile`、`thumbnail_ref`；
- `generation_jobs`：增加当前阶段、最后心跳、租约、请求指纹、Draft 版本和最终版本；
- `scenes`：增加当前 Final 版本、最近 Draft、缩略图和归档状态。

大型纹理、glTF 和缩略图不存 MySQL BLOB。V2 本地开发可先使用受控文件目录；部署时通过 Storage Adapter 接入对象存储。

## 11. API 变化

### 创建任务

`POST /api/v2/generations`

```json
{
  "prompt": "A rainy cyberpunk ramen alley at night",
  "preferences": {
    "styleKit": "cyberpunk_tokyo_v1",
    "quality": "balanced",
    "density": 0.7,
    "seed": 184726
  }
}
```

### 阶段事件

`GET /api/v2/generations/{jobId}/events`

SSE 事件类型：

- `job.status`；
- `stage.started`；
- `stage.completed`；
- `draft.available`；
- `final.available`；
- `job.failed`；
- `heartbeat`。

事件只包含可展示的阶段元数据和已验证版本引用，不传输未完成 LLM JSON。

### 受控修改

`POST /api/v2/scenes/{sceneId}/commands`

请求包含来源版本、自然语言指令或类型化命令、幂等键。成功后必须创建新 Scene Version。

### 版本与资产

- `GET /api/v2/scenes/{sceneId}/versions`；
- `POST /api/v2/scenes/{sceneId}/versions/{versionId}/restore`；
- `POST /api/v2/scenes/{sceneId}/duplicate`；
- `DELETE /api/v2/scenes/{sceneId}`；
- `GET /api/v2/style-kits`；
- `GET /api/v2/assets/{assetId}/metadata`。

V1 API 在 V2 开发期保持可用。V2 稳定后再宣布弃用周期，不直接破坏现有本地历史。

## 12. 非功能指标

### 12.1 生成体验

| 指标 | V2 目标 |
| --- | --- |
| 创建任务 API | P95 ≤ 300 ms，不含排队 |
| 首个阶段状态 | P95 ≤ 1 秒 |
| 可探索 Blockout | P50 ≤ 12 秒，P95 ≤ 30 秒 |
| Balanced Final | P50 ≤ 45 秒，P95 ≤ 120 秒 |
| 基准 Prompt 最终成功率 | ≥ 95%，至少 50 条 Prompt |
| 页面刷新后任务恢复 | 100% 恢复已持久化阶段 |
| Scene Plan completion tokens | P95 ≤ 1,200 |

如果仅使用 Kimi K3 无法达到 Blockout 时延目标，V2 必须通过模型路由、缓存或本地模板 Draft 解决，不能再次单纯提高超时上限来宣称通过。

### 12.2 视觉质量

建立人工盲测量表，每个场景按 1～5 分评价：

- Prompt 语义符合度；
- 构图与可行走性；
- 材质与灯光一致性；
- 细节密度与重复感；
- 整体审美和可辨识度。

发布门槛：

- 50 条基准 Prompt 平均每项 ≥ 4.0；
- V2 与 V1 盲测偏好率 ≥ 75%；
- 严重穿模、出生点阻塞或主题错误比例 < 3%；
- 三个首发 Style Kit 均必须在对应基准集独立通过。

### 12.3 Runtime 性能

- Balanced 档 1080p 目标 ≥ 50 FPS；
- 集成显卡 Draft 档目标 ≥ 45 FPS；
- 默认 draw calls ≤ 150；
- 默认可见三角形建议 ≤ 300k，硬上限 800k；
- 同屏阴影灯光 ≤ 2；
- 纹理显存估算 Balanced ≤ 256 MB；
- 失焦自动降帧或暂停；
- WebGL context 丢失后可恢复或展示明确降级页。

## 13. 安全、隐私和资产边界

- Kimi Token 和 Storage 凭据只在服务端 Secret 中；
- Prompt、Plan、Scene JSON 和资产元数据都视为不可信输入；
- Plan/Command/Scene 分别使用独立严格 Schema；
- LLM 不决定真实文件路径、URL、数据库 ID 或许可证；
- Asset Resolver 负责 URI 白名单、MIME、大小、哈希和许可证检查；
- 不执行 glTF extras 中的脚本或未知扩展；
- 不允许 Scene JSON 自带 Shader 源码；自定义材质必须来自已注册 Material ID；
- 用户删除场景时同时清理版本、命令、缩略图引用和匿名归属记录；
- 日志只保留安全元数据，完整 Prompt/Plan 的调试保留必须可配置且有期限；
- 成本限制按会话、Provider 和时间窗口执行，取消后停止后续增强阶段。

## 14. 明确范围

### V2 必须

- Scene Plan 1.0 与严格 Schema；
- Procedural Compiler 与至少三个 archetype；
- Scene JSON 2.0、V1 Migrator 和双版本 Runtime；
- 三个 Style Kit；
- Asset/Material Resolver 与一个策展基础资产包；
- Draft/Final 渐进生成和 SSE；
- 持久任务阶段与 Worker 边界；
- Draft、Balanced、Quality 三档；
- 缩略图和版本时间线；
- 至少四类受控局部命令；
- 50 条基准 Prompt、视觉量表和性能采样。

### V2 可选

- A/B seed 变体预览；
- 环境音与简单空间音频；
- 用户上传 glTF 的隔离检查流程；
- AI 纹理 Provider 实验；
- 只读分享链接；
- 移动端只读查看器。

可选项不得阻塞必须项验收。

### 明确不进入 V2

- AI 生成 Mesh；
- 任意第三方模型市场搜索与自动下载；
- NPC、对话、行为树和导航网格；
- 完整刚体物理、破坏、布料和流体；
- 多人实时协作与版本合并；
- 无限世界、体素编辑和区块流送；
- VR/AR；
- 完整移动端创作；
- 用户自定义脚本、Shader 或插件执行；
- 生产级订阅、计费、组织和权限系统；
- 在缺少基准数据前拆分微服务。

## 15. 实施里程碑

### M0：冻结基线与测量

- 保存 V1 快照并记录校验值；
- 建立 50 条 Prompt 基准集；
- 自动记录 V1 时延、tokens、成功率、节点数和截图；
- 初始化 Git 仓库并把 V2 开发纳入版本控制。

完成标准：任何 V2 结果都可以与 V1 同 Prompt、同 seed 对比。

### M1：Scene Plan 与 Blockout

- 定稿 Plan Schema；
- Kimi Plan Provider；
- 三个 archetype 的 Procedural Compiler；
- Draft Scene 生成与 V1 Runtime 临时适配。

完成标准：至少 45/50 Prompt 能生成可行走 Blockout，Plan P95 tokens ≤ 1,200。

### M2：Runtime 2.0 与视觉系统

- Scene JSON 2.0 与 Migrator；
- Procedural/Asset/Prefab/Instances/Decal Registry；
- 三个 Style Kit 与基础资产包；
- PBR、LOD、Instancing、Lighting Rig 和质量档。

完成标准：三类场景能稳定表现风格差异，V1 文档仍可打开。

### M3：渐进体验

- 持久 Stage Runner；
- SSE 与轮询降级；
- Draft/Final 切换、计时、取消、刷新恢复；
- 缩略图和版本时间线。

完成标准：增强失败时 Draft 仍可使用，后端重启后任务状态可恢复。

### M4：局部修改

- Command Schema 与 Compiler；
- 至少四类命令；
- 新版本、恢复、派生和变更摘要；
- 命令级幂等、失败与回滚测试。

完成标准：修改环境或风格不重新生成完整布局，旧版本不可变。

### M5：质量与发布门槛

- 50 Prompt 全量回归；
- 视觉盲测；
- FPS、draw calls、纹理和内存测试；
- 安全、资产许可证、删除和保留策略复核；
- 更新部署、恢复与验收文档。

完成标准：第 12 节指标和第 16 节验收全部通过。

单人开发建议按 6～8 周规划，实际节奏以资产准备和基准测试结果为准；不要为了赶时间同时引入微服务、AI 纹理和多人系统。

## 16. V2 验收标准

使用至少以下五类 Prompt：赛博朋克街巷、自然神社、温馨室内、荒漠站点、中文古镇；每类不少于 10 条。

必须同时满足：

1. Kimi 输出 Scene Plan，不直接输出大量底层 Primitive；
2. Plan、Command 和 Scene 经过各自 Schema 与语义校验；
3. 至少三个 archetype 和三个 Style Kit 可用；
4. 用户能在 Final 前进入 Blockout；
5. 取消或最终增强失败时保留有效 Draft；
6. 资产全部来自 Catalog，场景中不存在任意远程 URL；
7. 相同版本、seed 和配置产生可重复结构；
8. V1 场景可迁移并在 Runtime 2.0 中打开；
9. 用户能执行至少四类局部命令并获得新版本；
10. 历史展示缩略图、版本状态和变更摘要；
11. 后端重启后任务状态和有效检查点不会丢失；
12. 50 Prompt 成功率、生成时延和视觉评分达到第 12 节门槛；
13. Balanced 1080p 达到目标 FPS，且预算超限时自动降级；
14. 单资产、单节点或单增强阶段失败不拖垮整个场景；
15. 自动化测试覆盖协议迁移、程序化编译、资产解析、任务恢复、命令和关键 E2E；
16. 仓库、构建产物、日志和资产元数据中不存在真实凭据。

## 17. 风险与控制

| 风险 | 控制 |
| --- | --- |
| Kimi Plan 仍然慢 | 限制输出体积；缓存；Provider 路由；本地模板 Draft；不靠无限延长超时 |
| 程序化场景看起来重复 | 多 archetype、Style Kit 权重、seed 变体、Hero Anchor 和视觉盲测 |
| 资产使包体失控 | Catalog 元数据、按需加载、KTX2、LOD、对象存储和预算阻断 |
| Scene JSON 2.0 破坏历史 | 只读 V1、显式 Migrator、夹具测试、不可变原始版本 |
| 局部修改破坏空间 | 类型化命令、来源版本锁、约束重算、生成新版本 |
| 持久 Worker 增加复杂度 | 先采用 MySQL 租约与单 Worker，接口稳定后再替换基础设施 |
| 视觉评价主观 | 固定量表、同 Prompt 盲测、截图基线和严重错误统计 |
| 高质量档拖垮低端设备 | 自动能力探测、质量档、LOD、Instancing、纹理与阴影预算 |

## 18. 已固定决策与待确认事项

### 已固定

- Scene JSON 继续作为运行时协议；
- 新增 Scene Plan，LLM 不再逐节点完成完整世界；
- V2 使用程序化编译器和策展资产提升一致性；
- 所有修改创建不可变新版本；
- 资产和材质必须经过 Catalog/Resolver；
- 模块化单体、MySQL 和可替换 Provider 保持不变；
- V2 优先体验与视觉质量，不扩展 NPC、物理和多人能力。

### 实现前需要确认

1. 三个首发 Style Kit 是否采用本文建议，还是替换其中一个；
2. V2 是否允许引入策展 CC0/商业可用资产包，以及许可证接受范围；
3. 部署仍只面向本机，还是需要公网单用户版本；
4. 匿名场景是否允许删除，默认保留期是否继续为 30 天；
5. 是否接受新增独立 Worker 进程但暂不新增 Redis；
6. V2 是否需要中文与英文 UI 同时作为验收项；
7. Quality 档是否允许首次加载额外下载较大的纹理与模型资源；
8. 是否把只读分享链接列入 V2 可选项，还是完全推迟。

这些问题会影响资产、部署和工期，但不会改变“Scene Plan + Procedural Compiler + Scene JSON 2.0”的主架构。
