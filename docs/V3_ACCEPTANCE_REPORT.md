# Prompt to World V3 验收报告

日期：2026-08-31  
结论：通过 V3 首版验收，可作为本地默认生成链路继续迭代。

## 1. 交付结论

V3 已从“为 Prompt 选择一个相近模板”改造成“先理解实体与关系，再从受控能力编译场景”。系统现在以 Scene Intent 2.0 为语义事实来源，以 Scene JSON 3.0 为运行时事实来源，并在 Final 前执行确定性相关性门禁。

本轮同时保留 V1 / V2 API、协议和历史场景读取能力。V3 不覆盖历史 Scene JSON；失败、超时和取消仍保留可探索 Draft。

## 2. 已完成范围

### 2.1 语义与编译

- Scene Intent 2.0 Schema、语义校验器和 Kimi 结构化意图编译；
- 开放实体、关系、禁止项、环境、主角镜头、质量和 seed；
- V3 Capability Registry，支持 exact、abstract 与显式降级；
- 分隔符同义词归一化，例如 `starfield`、`star_field` 和 `star-field` 视为同一能力；
- 六种场景模式：walkable、interior、orbital、flythrough、diorama、panorama；
- 确定性布局求解、空间关系、主角构图和模式化相机；
- Visual Recipe Compiler 与 Scene JSON 3.0；
- Fidelity Gate：required coverage、relations、forbidden、unrelated ratio、hero visibility。

### 2.2 视觉与运行时

- 深空星场、恒星、脉冲星、黑洞、行星、陨石坑、云层等引擎内置效果；
- 城市、商铺、霓虹、室内、图书馆、森林、沙漠、古镇、水下和浮岛配方；
- 非步行场景不再强制地面、道路或第一人称相机；
- orbital、flythrough、panorama、diorama 使用轨道式观察；walkable 和 interior 保留第一人称探索；
- 所有可见节点带 provenance，可追溯到用户实体、系统结构或风格增强。

### 2.3 产品体验

- 生成前即时显示“我理解为”、场景模式和关键实体；
- Draft 可探索后继续后台增强，页面无需等待 Final 才可用；
- 进度文案改为理解描述、匹配能力、构建草稿、视觉增强、核对画面、完成；
- 抽象表现会明确告知，不用无关模板掩盖能力缺口；
- 点击场景对象可查看出现原因、来源、能力版本、匹配度和移除入口；
- 支持切换探索模式、环境、风格、密度，以及按实体或语义移除；
- 所有编辑继续创建不可变版本，可恢复、复制和软删除。

### 2.4 API 与数据

- 新增 `/api/v3` 健康检查、生成、SSE、场景、版本、恢复、命令、复制、删除、风格和能力目录接口；
- MySQL 继续保存场景、版本、任务、阶段、命令和 Scene Intent；
- V2 与 V3 Worker 按 apiVersion 分流，避免任务竞争；
- Kimi Provider 保持独立，Token 仅由后端环境变量读取。

## 3. 自动化验收结果

| 验收项 | 结果 |
|---|---|
| V3 Prompt 基准 | 100 条，覆盖 10 类主题 |
| 后端 Schema、单元与 API 集成测试 | 22 通过 |
| V3 专项测试 | 8 通过 |
| 前端测试 | 3 通过 |
| 前端代码检查 | 通过 |
| TypeScript 与生产构建 | 通过 |
| V1 / V2 历史读取 | 通过，浏览器实测 V1 场景可打开 |
| 页面控制台未处理异常 | 0 |

质量档测试确认：同一 Prompt 的 Draft 与 Quality 语义实体集合不变，只调整细节和渲染预算。未知概念测试确认：使用明确的抽象标记，不生成无关 archetype。关系引用、Scene Intent 和 Scene JSON 均经过严格校验。

## 4. 关键真实案例

真实 Kimi K3 输入：

> 深空中一颗耀眼恒星，旁边是一颗脉冲星；远处有一个黑洞，群星作为背景。

实测结果：

- Scene Mode：orbital；
- 识别实体：恒星、脉冲星、黑洞、群星背景；
- required coverage：4/4；
- Final：5 个节点，其中 4 个语义对象、1 个结构光源；
- 关系：脉冲星靠近恒星，黑洞远离恒星；
- 未出现月面道路、研究舱、太阳能板、树木、店铺或拉面元素；
- 黑洞与脉冲星的抽象表现已在界面中主动说明；
- Draft 即时可见，当前网络环境下 Final 约 38 秒完成；
- 页面控制台没有 error 或 warning。

真实请求还暴露并修复了一个同义词边界：Kimi 返回 `star_field` 时，旧匹配器会将其与 `starfield` 分开，导致群星重复。现在先执行去分隔符精确匹配，再进行模糊匹配，并已有回归测试锁定。

## 5. 技术边界

V3 当前提供高辨识度的程序化/抽象视觉，不宣称具备照片级真实 3D 模型生成。以下内容仍不进入本版：

- 任意 AI 生成 3D Mesh、骨骼或动画；
- 未审核的远程模型、纹理、Shader 或脚本；
- NPC、对话、任务、物理破坏和多人联机；
- 无限世界、体素编辑和 Minecraft 式持续生成；
- 完整专业关卡编辑器和自由拓扑建模。

黑洞、脉冲星等高级天体目前使用引擎内置抽象效果；能力目录和视觉配方均可版本化扩展，后续可以替换为受信 GLTF、程序化生成器或 AI 资产，而不修改 Prompt 层和 Scene Intent。

## 6. 已知非阻塞项

- Three.js 生产块约 1.09 MB，已与主界面分离并延迟加载；Vite 仍提示单块超过 1 MB，后续可继续拆分后处理和 Three 扩展包；
- Final 时延主要受 Kimi 网络响应影响，Draft 已隔离等待成本；
- 当前能力目录优先覆盖高复用主题，长尾概念会诚实使用抽象表现；
- 自动化浏览器验收覆盖桌面主流程；移动端触控漫游和低端设备性能需在部署阶段建立设备矩阵。

## 7. 复验命令

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe smoke_kimi_v3.py

cd ..\frontend
npm run lint
npm run test -- --run
npm run build
```

`smoke_kimi_v3.py` 会消耗一次真实 Kimi 调用；常规自动化测试不会消耗 Token。

## 8. 最终判断

V3 已满足本轮最重要的产品判断：用户描述深空天体时，系统生成深空天体；用户描述月面研究站时，系统只组合月面能力；未知内容会被明确说明，而不是伪装成另一个熟悉模板。

这使项目具备继续扩展为 AI 场景编辑器的稳定基础：语义层开放，能力层受控，运行时可替换，历史数据兼容，质量门禁可测试。
