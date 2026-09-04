# Prompt to World V3 产品需求与技术边界

> 文档状态：V3 开发基线  
> 核心主题：描述什么，就生成什么；做不到时，明确告诉用户  
> 前置版本：V2 已完成 Prompt → Draft → Kimi Scene Plan → Procedural Compiler → Scene JSON 2.0 → 3D World

## 0. 执行摘要

V3 不以“堆更多特效”为目标，而是解决 V2 最影响信任感的问题：用户描述的关键物体、空间关系和场景类型，必须真实进入最终世界。

V3 核心链路：

    Prompt
      ↓
    Scene Intent 2.0
      ↓
    Capability Resolver
      ↓
    Layout / Constraint Solver
      ↓
    Visual Recipe Compiler
      ↓
    Scene JSON 3.0
      ↓
    3D Runtime
      ↓
    Semantic Fidelity Evaluator

V3 采用“开放语义、封闭执行”：

- 用户可以描述任意主题，不再被迫匹配少数固定场景模板；
- LLM 只输出受约束的场景意图，不生成代码、Shader、模型地址或 Three.js；
- 引擎只执行注册过、可测试、可限制预算的视觉能力；
- 未支持的概念使用相关的抽象表现，或清楚提示暂不支持；
- 第一屏必须能看出主题，系统在标记“完成”前验证关键意图是否落地。

一句话定义 V3：

> 从“选择最接近的模板”升级为“解析实体与关系，再用可扩展能力组合场景”。

---

## 1. V2 问题与根因

### 1.1 已观察到的问题

用户描述恒星、脉冲星、黑洞与群星时，LLM 已正确识别这些内容，但最终画面仍出现月面研究站、蓝色陨石坑、太阳能板、轨道和月岩。

这不是用户提示词写得不够好，也不主要是 LLM 理解失败，而是编译阶段丢失了已经理解的意图。

### 1.2 根因

1. Scene Plan 只能从少量封闭 archetype 中选择，开放主题会被压缩成“最接近”的模板。
2. archetype 编译器硬编码内容，mustInclude、avoid 和 visualDirection 没有成为强约束。
3. 所有场景默认要求道路、地面与可步行结构，不适用于深空、轨道、全景和微缩场景。
4. 高质量档会追加固定道具，视觉质量选项意外改变语义内容。
5. 生成完成只代表 Scene JSON 合法，不代表画面与提示词相关。

### 1.3 V3 纠正原则

- archetype 只能作为可选构图预设，不能决定用户没有要求的内容；
- entities 和 relations 是内容事实来源；
- 质量档只能改变细节与渲染预算，不能增加新的主题物品；
- 场景模式决定相机与空间规则，不再给所有场景套用步行巷道；
- Schema 合法与语义正确分别验证。

---

## 2. 产品原则

### 2.1 人性化

1. 不要求用户学习提示词工程，普通自然语言应当可用。
2. 不让用户猜系统理解了什么，生成时展示简短的“我理解为”摘要。
3. 不静默偷换概念，无法精确表现时说明将使用何种抽象形式。
4. 默认界面保持一句话、一个主按钮，高级能力按需展开。
5. 出错时保留可探索草稿、用户修改和历史版本，不让等待白费。
6. 进度文案使用用户能理解的阶段，不暴露内部服务术语。
7. 系统自动添加的物体必须可解释、可定位、可删除。

### 2.2 实用性

1. 先提高相关性、首屏识别度和稳定性，再提高模型真实度。
2. 保留 V2 能力，通过适配器渐进迁移，不整体推倒重写。
3. 优先使用注册表、程序化配方和 Primitive 组合，不依赖昂贵的 AI 3D 生成。
4. 使用模块化单体，V3 不引入微服务、消息中间件和复杂分布式系统。
5. 每个里程碑都可独立演示、测试和回退。
6. 以自动化基准 Prompt 和真实失败样例驱动开发，不凭主观截图判断完成。

---

## 3. 目标与非目标

### 3.1 产品目标

- 任意主题不再被强制塞入最接近的固定模板。
- 用户要求的关键实体、禁止项和空间关系能进入最终场景。
- 支持步行、室内、轨道、飞越、微缩、全景等场景模式。
- 第一屏优先展示主角物体，用户无需移动相机才能理解主题。
- 未知概念可以安全抽象，并向用户说明表现方式。
- 修改实体、关系、风格和环境时，不必整场重新生成。
- 新增场景能力主要通过注册表与视觉配方扩展，不修改核心链路。

### 3.2 技术目标

- 引入 Scene Intent 2.0、Scene JSON 3.0 和版本迁移策略。
- 建立实体能力注册表、关系约束求解器、视觉配方编译器。
- 为每个运行时节点记录来源和生成理由。
- 建立确定性的语义忠实度评估与完成门禁。
- 保持 Provider 抽象，Kimi K3 是首个 Provider，但不写死在业务中。
- 相同 Prompt、控制项、seed 和能力版本下可重现。

### 3.3 V3 明确不做

- 不生成或执行任意 JavaScript、Three.js、Shader 与用户脚本。
- 不承诺照片级真实、影视级渲染或科学模拟精度。
- 不做任意 AI Mesh、无限世界、多人联机、NPC 社会系统、完整物理破坏。
- 不做 Blender 替代品或专业 DCC 编辑器。
- 不允许 LLM 选择任意远程 URL、本地文件或未经审核的模型。
- 不因“高质量”自动加入与主题无关的复杂物品。

---

## 4. 核心用户体验

### 4.1 默认生成流程

1. 用户输入一句自然语言并点击“生成世界”。
2. 系统立即保留输入，并展示“我理解为”摘要：
   - 场景模式；
   - 关键实体；
   - 主要空间关系；
   - 时间、天气与风格；
   - 需要抽象表现或暂不支持的内容。
3. 确定性 Draft 尽快出现，可立即查看。
4. 后台完成能力匹配、构图与视觉增强。
5. 完成前执行相关性核对。
6. Final 替换 Draft；若核对失败，保留 Draft 并给出具体原因与修正入口。

“我理解为”不是强制确认向导。用户可以不操作继续生成，也可直接修改错误的实体标签或关系。

### 4.2 进度阶段

- 正在理解描述
- 正在匹配场景能力
- 正在安排空间与镜头
- 探索草稿已就绪
- 正在增强视觉细节
- 正在核对描述与画面

### 4.3 诚实降级

能力不足时使用明确反馈：

- “黑洞将使用抽象吸积盘与引力光环表现。”
- “暂不支持真实流体模拟，将使用静态水面效果。”
- “未找到可用表现方式：生物机械鲸。你可以移除它或使用抽象轮廓。”

禁止用“生成成功”掩盖关键实体缺失，也禁止自动替换为无关 archetype。

### 4.4 局部修改

V3 至少支持：

- 添加、删除、替换实体；
- 调整前后、远近、环绕、内部等关系；
- 改变场景模式、时间、天气、风格和质量；
- 重新构图但保留实体；
- 重新视觉化单个实体；
- 恢复任意历史版本。

命令必须结构化执行，不能把自然语言直接拼接为代码。

---

## 5. Scene Intent 2.0

Scene Intent 是“用户到底想看什么”的稳定协议，独立于 Three.js、资产 ID 和具体渲染方案。

### 5.1 顶层结构

    {
      "schemaVersion": "2.0",
      "title": "深空恒星观测",
      "sceneMode": "orbital",
      "environment": {},
      "entities": [],
      "relations": [],
      "constraints": {},
      "cameraIntent": {},
      "styleIntent": {},
      "quality": "balanced",
      "seed": 18426
    }

### 5.2 实体

每个实体至少包含：

- id：稳定且唯一；
- concept：开放概念，例如 star、pulsar、black_hole、ramen_shop；
- category：受控大类，例如 celestial、architecture、nature、prop、effect；
- role：hero、supporting、background、structural；
- importance：0 到 1；
- count：数量或范围；
- attributes：颜色、尺度、状态等受控属性；
- sourceText：对应的原始描述片段。

concept 允许开放扩展，category、role 和属性结构保持封闭，以兼顾灵活性和执行安全。

### 5.3 关系

首批只支持高价值、可稳定求解的关系：

- left_of、right_of、in_front_of、behind；
- near、far_from；
- inside、around、orbiting；
- above、below；
- facing、connected_to。

未支持的复杂关系不得被悄悄解释为另一种关系。

### 5.4 约束

constraints 至少包含：

- requiredEntities：必须出现；
- forbiddenConcepts：不得出现；
- optionalEntities：预算允许时出现；
- maxUnrelatedObjects：系统可添加的无关语义物体上限，默认 0；
- preserveOpenSpace：是否保留视野或通道；
- navigationRequired：是否必须可行走。

### 5.5 archetype 的新定位

archetypePreset 改为可选字段，仅用于复用成熟构图，如窄巷、庭院、空间站模块群。

它必须满足：

- 不覆盖 entities、relations 和 forbiddenConcepts；
- 不自动引入新主题；
- 可以完全不使用；
- 添加内容必须标记来源并进入语义评估。

---

## 6. 场景模式

| 模式 | 适用场景 | 必需能力 | 不应强制 |
|---|---|---|---|
| walkable | 街道、庭院、户外关卡 | 地面、碰撞、步行相机 | 固定远景主体 |
| interior | 房间、舱室、店铺 | 边界、出入口、室内相机 | 无限地面 |
| orbital | 星球、空间站、天体关系 | 轨道相机、尺度分层、远景层 | 道路与重力地面 |
| flythrough | 云层、洞穴、抽象通道 | 路径、镜头安全区 | 固定步行平面 |
| diorama | 微缩景观、展示模型 | 轨道相机、可见边界 | 真实比例与碰撞 |
| panorama | 星空、地平线、氛围空间 | 全景背景、有限焦点 | 可行走物体 |

场景模式决定相机、坐标层和必要结构，但不能决定用户主题。

---

## 7. 能力注册表与视觉配方

### 7.1 Entity Capability Registry

每项能力记录：

- capabilityId 与版本；
- 支持的 concept、别名与 category；
- 适用 sceneMode；
- 可调参数及安全范围；
- 对应 Visual Recipe；
- 节点、灯光、材质和性能预算；
- 支持程度：exact、abstract、unsupported；
- 降级策略与用户提示。

### 7.2 匹配顺序

1. 精确概念能力；
2. 已登记别名；
3. 同类可接受的抽象能力；
4. 受控 Primitive Blueprint；
5. 明确标记 unsupported。

禁止回退到“最近但不相关的场景模板”。

### 7.3 Visual Recipe

Visual Recipe 是引擎维护的安全配方，可组合：

- Primitive、Prefab、受信资产；
- ring、orbit、scatter、cluster、path、shell、beam 等布局算子；
- 注册过的材质与引擎内置效果；
- 灯光、雾、背景和镜头规则；
- 明确的节点与性能预算。

LLM 只能引用语义概念和受控参数，不能编写配方实现。

### 7.4 首批高复用能力

- 环境：starfield、sky、terrain、water、fog、cloud；
- 天体：star、pulsar、black_hole、planet、moon、asteroid；
- 建筑：building、room、station_module、bridge、tower、shop；
- 自然：tree、rock、grass、flower、forest_cluster；
- 道具：sign、lamp、table、bench、antenna、solar_panel；
- 表现：neon、glow、trail、horizon、crater；
- 布局：street、courtyard、interior_shell、orbital_system、scatter_field。

已有 V2 模板拆分为能力与配方继续复用，不直接删除。

---

## 8. 构图与空间约束

Layout Solver 把语义关系转换为空间位置，不依赖 LLM 输出大量坐标。

### 8.1 空间分层

- foreground：前景与视觉引导；
- navigable：可进入或可交互的主体空间；
- distant：远处但有辨识度的对象；
- background：天空、星场、地平线等背景层。

### 8.2 求解优先级

1. 安全与预算约束；
2. requiredEntities；
3. hero 首屏可见；
4. 用户明确关系；
5. 场景模式规则；
6. 可选装饰与风格细节。

### 8.3 相机要求

- hero 实体在初始镜头可见且不被严重遮挡；
- first frame 表达主要主题和核心关系；
- 不同 sceneMode 使用对应控制器；
- 自动构图失败时使用保守镜头，不把主角放到相机背后；
- 支持重置镜头与“聚焦此物体”。

---

## 9. 节点来源与语义忠实度

### 9.1 节点来源

Scene JSON 3.0 中每个可见节点包含 provenance：

- entityId：对应哪个意图实体；
- origin：prompt、structural、style、system、legacy；
- resolver：使用了哪项能力与版本；
- reason：为什么存在；
- confidence：匹配置信度；
- userRemovable：是否允许删除。

结构节点只能满足碰撞、边界、相机和构图需求；风格节点只能增强已有语义，不能创造新主题。

### 9.2 完成前评估

- required coverage：必需实体覆盖率；
- relation satisfaction：空间关系满足率；
- forbidden violations：禁用概念违规数；
- unrelated ratio：无来源或无关物体比例；
- hero visibility：主角首屏可见性；
- capability disclosure：抽象与不支持项是否已告知用户。

### 9.3 完成门禁

- 必需实体覆盖率不低于 95%；
- 明确空间关系满足率不低于 90%；
- forbidden violations 为 0；
- hero 首屏可见率为 100%；
- 未知概念被无关模板替换的比例为 0；
- 非结构性无关物体比例不高于 10%，默认目标为 0。

未通过时允许一次确定性修复。仍失败则返回“部分完成”，保留 Draft 并列出缺失项，不能伪装成成功。

---

## 10. 前端需求

### 10.1 保持简单

默认生成页继续保留场景描述、生成按钮、风格、质量、Draft / Final 状态和进入场景。新增信息渐进展示，不把首页变成专业编辑器。

### 10.2 新增组件

- 意图摘要条：场景模式、关键实体和关系；
- 能力提示：精确表现、抽象表现、暂不支持；
- 相关性结果：例如“已表现 5/5 个关键内容”；
- 物体来源面板：点击对象查看来源和生成原因；
- 局部修正入口：删除、替换、聚焦、重新表现；
- 版本差异摘要：说明改了哪些实体、关系和视觉属性。

### 10.3 可用性与无障碍

- 键盘可完成输入、生成、取消、进入和退出场景；
- 明确显示鼠标锁定与退出方式；
- 尊重 prefers-reduced-motion；
- 文字与按钮满足可读对比度；
- 3D 加载失败时仍可查看意图、历史与错误原因；
- 移动端以查看和轻量编辑为主，不承诺完整第一人称操作。

---

## 11. 后端与数据边界

### 11.1 模块

- Intent Compiler：Prompt → Scene Intent 2.0；
- Intent Validator：协议与语义约束；
- Capability Registry：概念与能力匹配；
- Entity Resolver：表现选择与降级；
- Layout Solver：关系、分层和镜头；
- Recipe Compiler：Visual Recipe → Scene JSON 3.0；
- Fidelity Evaluator：相关性评估与完成门禁；
- Scene Migrator：V1 / V2 / V3 兼容；
- Provider Adapter：Kimi 与未来模型；
- Generation Orchestrator：Draft、Final、取消、恢复和事件。

### 11.2 数据策略

V3 继续使用 MySQL。第一阶段优先在现有版本记录中增加 JSON 字段：

- scene_intent；
- resolution_trace；
- fidelity_report；
- capability_versions；
- unsupported_entities。

能力目录与 Visual Recipe 初期使用仓库内版本化文件；只有出现在线运营、灰度与多人协作需求后再独立建表。

### 11.3 API 原则

- V3 使用独立版本路由，避免破坏 V2；
- 生成响应包含 intentPreview、coverage 和 unsupportedEntities；
- Draft 与 Final 延续异步任务和 SSE；
- 局部命令使用受控操作类型；
- 相同幂等键不得重复消费 Provider；
- 删除使用软删除，版本保持不可变。

---

## 12. 质量、风格与性能边界

### 12.1 质量档

质量档只影响几何细分、实例预算、阴影、后处理、材质复杂度、纹理分辨率和可选微细节。

质量档不得改变 requiredEntities、forbiddenConcepts、实体语义数量、明确关系和 sceneMode。

### 12.2 风格

Style Kit 负责颜色、材质、光照、雾、轮廓和装饰语言。它可以改变同一物体“怎么画”，不能决定“画什么”。

### 12.3 性能目标

- 生成请求确认 P95 不高于 300ms；
- Scene Intent 可见 P95 不高于 8 秒；
- Intent 完成后 Draft P95 不高于 3 秒；
- Balanced Final P95 不高于 60 秒，不包含 Provider 大范围故障；
- Provider 超时或失败时 Draft 始终可保留；
- 桌面端 1080p Balanced 目标 45 FPS，最低可接受 30 FPS；
- 单场景受节点、灯光、阴影、实例和显存预算约束。

超时提示应区分仍在排队、Provider 超时、编译失败、相关性核对失败，不再统一显示“请简化描述”。

---

## 13. 迁移与实施顺序

### 阶段 0：冻结问题与基准

- 将当前深空失败样例加入回归集；
- 扩展为至少 100 条 Prompt，覆盖 10 类主题和跨模板描述；
- 保存 V2 结果作为对照，不再向 V2 添加关键词补丁。

### 阶段 1：Intent 与相关性门禁

- 完成 Scene Intent 2.0；
- 实现意图摘要 UI；
- 建立 provenance 和 Fidelity Evaluator；
- 可暂时通过适配器调用 V2 编译器。

### 阶段 2：能力注册表

- 建立 capability schema、版本与测试；
- 上线首批高复用能力；
- 实现 exact、abstract、unsupported 降级链；
- 禁止 nearest-archetype 静默替换。

### 阶段 3：场景模式与布局求解

- 上线 orbital、panorama、walkable、interior；
- 实现分层、关系约束和 hero 镜头；
- 首个完整回归目标为恒星、脉冲星、黑洞场景。

### 阶段 4：运行时与局部编辑

- Scene JSON 3.0 Runtime；
- 模式化相机控制器；
- 物体来源面板与局部命令；
- V2 → V3 适配与历史兼容。

### 阶段 5：视觉质量与发布

- 扩展 Visual Recipe 和受信资产；
- 完成性能预算、浏览器验收和失败恢复；
- 达到语义、性能、稳定性和无障碍指标后默认启用 V3。

每个阶段使用功能开关发布，可独立回滚。V2 在迁移期保持可读、可运行，不覆盖历史 Scene JSON。

---

## 14. 验收标准

### 14.1 必测场景

- 赛博朋克拉面巷；
- 月面研究站与蓝色陨石坑；
- 仅包含恒星、脉冲星、黑洞和群星的深空场景；
- 室内图书馆；
- 云层中的浮岛；
- 沙漠遗迹；
- 海底实验室；
- 抽象几何展览；
- 明确禁止树木的城市广场；
- 包含系统未知概念的场景。

### 14.2 自动化验收

- 100 条以上回归 Prompt；
- 同 Prompt、seed、控制项、能力版本可重现；
- required coverage、relations、forbidden 和 hero visibility 达标；
- 未知概念不产生无关 archetype；
- V1 / V2 场景可继续打开；
- Provider 失败、超时、取消、刷新后恢复均可测试；
- Schema、迁移、单元、集成和浏览器端到端测试通过；
- 生产构建通过，控制台无未处理异常。

### 14.3 关键案例通过定义

输入“在浩瀚宇宙中，前方是一颗耀眼恒星，旁边是一颗脉冲星，远处有一个黑洞，远处群星点点”时：

- sceneMode 为 orbital 或 panorama；
- 恒星、脉冲星、黑洞和星场均为 required；
- 初始镜头能看到主要恒星与脉冲星，并辨认远处黑洞；
- 不出现月面道路、研究舱、太阳能板、树木或拉面店；
- 如黑洞只支持抽象表现，生成前或生成中告知用户；
- 相关性门禁通过后才显示“完成”。

---

## 15. 安全、成本与风险

### 15.1 安全边界

- Kimi Token 只在后端环境变量中读取；
- Prompt、Intent 与 Scene JSON 均视为不可信输入；
- 禁止动态代码执行、任意 URL、任意文件路径和未登记 Shader；
- 资产按白名单、许可证和大小限制接入；
- 所有实体、节点、灯光和后处理受硬预算限制；
- 日志不记录密钥与完整敏感配置。

### 15.2 主要风险与控制

| 风险 | 控制方式 |
|---|---|
| 开放概念无限增长 | category 受控、能力注册表、明确降级链 |
| 布局求解过度复杂 | 只支持有限高价值关系，逐步扩展 |
| 抽象表现过于相似 | 可版本化 Visual Recipe 与视觉基准图 |
| LLM 评估不稳定 | 确定性覆盖检查为主，LLM 评审仅作辅助 |
| 生成延迟和成本上升 | Draft 优先、缓存 Intent、限制自动修复次数 |
| UI 变得专业而难用 | 一句话入口不变，高级信息渐进展开 |
| V2 历史数据失效 | 版本化协议、迁移器、legacy provenance |
| 资产版权与体积失控 | 受信目录、许可证字段、预算和缓存策略 |

---

## 16. 已确定决策

1. Scene Intent 是语义事实来源，Scene JSON 是运行时事实来源。
2. entities 与 relations 优先于 archetypePreset。
3. archetypePreset 可选，不能覆盖用户意图。
4. 质量和风格不能改变语义实体集合。
5. 所有可见节点必须可追溯。
6. 未支持概念不得替换成无关内容。
7. 非步行场景不强制地面、道路与第一人称相机。
8. V3 继续使用确定性编译与注册表，不让 LLM 生成代码。
9. V2 通过适配器渐进迁移，不整体重写。
10. 相关性核对通过是 Final 完成条件，不只是附加统计。

V3 的成功标准不是“能生成更多东西”，而是用户第一次看到结果时会自然地说：

> 对，这就是我刚才描述的世界。
