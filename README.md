# Prompt-To-3D-World

把自然语言描述编译成经过验证、可版本化、可探索的 3D 世界。

*A prompt-to-3D system that compiles natural-language descriptions into validated, versioned, and explorable worlds.*

## 版本与进度

- 当前版本：**3.0.0（V3）**
- 状态：V3 首版已完成本地验收，作为默认生成链路继续迭代
- 技术栈：React 19、React Three Fiber、Three.js、FastAPI、SQLAlchemy、MySQL 8

## 核心功能

- 将提示词转换为开放实体、空间关系、限制条件和场景模式。
- 通过能力注册表、布局求解器和视觉配方生成 Scene JSON 3.0。
- 先生成可立即探索的本地 Draft，再由 Kimi 增强为 Final。
- Fidelity Gate 核对必需实体、关系、禁止项和主角可见性。
- 支持实时进度、对象来源说明、结构化编辑、恢复、复制和软删除。
- V1/V2 场景与 API 保持兼容。

## 使用方式

需要 Python 3.12+、Node.js 20+ 和 MySQL 8。

先准备配置和后端：

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写 MySQL 配置；如使用 AI 增强，再填写 MOONSHOT_API_KEY

cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m app.bootstrap
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

另开终端启动前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>。API 文档位于 <http://127.0.0.1:8010/api/docs>。

## AI 辅助

运行时由 Kimi 解析语义意图，确定性编译器负责布局、能力匹配和最终 3D 结构；没有 API Key 时仍可使用本地 Draft。开发过程使用 AI 辅助架构拆解、实现与测试，最终产品和技术决策由作者确认。

## 验证

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest

cd ..\frontend
npm run lint
npm test
npm run build
```

详细范围与结果见 [V3 技术需求](docs/V3_PRODUCT_AND_TECHNICAL_REQUIREMENTS.md) 和 [V3 验收报告](docs/V3_ACCEPTANCE_REPORT.md)。
