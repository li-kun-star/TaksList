收到，先补一次可视化规范读取，然后输出 PRD 全文。

# 产品需求文档（PRD）· 桌面悬浮任务清单

| 文档信息 |  |
| --- | --- |
| 产品名称 | 桌面悬浮任务清单（暂定名 `FloatTask`） |
| 版本 / 状态 | v1.0 草案 · 待评审 |
| 日期 | 2026-10-15 |
| 技术栈 | Python + Tkinter + PyInstaller |
| 目标平台 | Windows 10 / 11（单文件 exe） |

---

## 1. 背景与目标

**背景**：日常有大量"随手记、马上做"的待办需求，希望清单常驻桌面、随时可见，但普通待办 App 需要切换窗口，打断工作流；同时希望数据完全本地、可整体迁移。

**产品目标**

- 常驻桌面：折叠为边缘悬浮胶囊，不遮挡操作区，一键展开/收起
- 秒级操作：新增、删除、勾选、编辑均一次点击/双击完成
- 数据本地化：`data.json` 与 exe 同目录，整体拷贝即迁移

**非目标（本期不做）**：云同步、多端、团队协作、到点提醒通知、任务分类/标签、拖拽排序、暗色模式。

---

## 2. 目标用户与使用场景

| 场景 | 描述 |
| --- | --- |
| 工作中 | 电脑前办公，胶囊贴右边缘常驻，随时展开看今日任务、勾选进度 |
| 开机即用 | 开机自启，无需手动启动 |
| 跨设备迁移 | 整个文件夹拷到另一台 Windows 电脑即可继续用 |

---

## 3. 产品概述

- **形态**：置顶无边框小窗口，两种状态——折叠态（边缘胶囊，仅图标）与展开态（任务面板）
- **核心流程**：启动 → 读取 `data.json` → 显示折叠胶囊 → 点击展开面板 → 增/删/勾/改 → 变更即写盘 → 点击外部收起

---

## 4. 功能需求（FR）

### 4.1 悬浮胶囊

| ID | 需求 | 优先级 |
| --- | --- | --- |
| FR-1 | 默认贴屏幕右边缘、垂直居中，置顶显示（`-topmost`） | P0 |
| FR-2 | 折叠态仅显示一个清单图标，尺寸紧凑 | P0 |
| FR-3 | 点击胶囊展开面板；点击面板外部或再次点击胶囊收起；不支持悬停触发 | P0 |

### 4.2 任务面板

| ID | 需求 | 优先级 |
| --- | --- | --- |
| FR-4 | 面板顶部显示当天日期 + 星期（如"2026年10月15日 周四"），非实时时钟 | P0 |
| FR-5 | 任务行 = 复选框 + 任务文字 + 计划时间（HH:MM） | P0 |
| FR-6 | 今日视图 = 所有未完成任务 + 今日勾选完成的任务（划线置灰、沉底显示）；昨日及更早的已完成任务不显示（仍在 JSON 中归档） | P0 |

### 4.3 任务操作

| ID | 需求 | 优先级 |
| --- | --- | --- |
| FR-7 | 新增：输入任务文字（必填）+ 计划时间（可选），回车或点击确认加入清单 | P0 |
| FR-8 | 勾选：点击复选框标记完成/取消完成，状态即时更新并落盘 | P0 |
| FR-9 | 编辑：双击任务行，可修改文字与时间 | P1 |
| FR-10 | 删除：任务行右侧删除按钮，直接删除（无二次确认） | P0 |
| FR-11 | 时间跨天：启动或跨零点时，所有未完成任务自动顺延，继续显示在今日视图 | P0 |

### 4.4 设置

| ID | 需求 | 优先级 |
| --- | --- | --- |
| FR-12 | 面板提供设置入口，含"开机自启"开关；开启时写入 Windows 注册表 `HKCU\...\Run`，关闭时移除 | P1 |
| FR-16 | 设置中可自定义任务区文字颜色（辅助文字、完成态色由正文色自动淡化推导，浅色文字往深色淡化、深色文字往纸色淡化）；修改后即时生效并落盘，旧 `data.json` 无此字段时沿用内置暖棕 | P1 |

### 4.5 数据持久化

| ID | 需求 | 优先级 |
| --- | --- | --- |
| FR-13 | 数据文件 `data.json` 存放于 exe 所在目录；任何变更（增/删/勾/改/设置）立即写入 | P0 |
| FR-14 | 启动时读取恢复；文件不存在则创建默认结构 | P0 |
| FR-15 | JSON 损坏容错：读取失败时备份为 `data.json.bak` 并重建空数据，不崩溃 | P1 |

---

## 5. 数据模型

```
{
  "tasks": [
    {
      "id": "a1b2c3d4",
      "text": "完成实验报告",
      "time": "14:00",
      "date": "2026-10-15",
      "done": false,
      "completedAt": null
    }
  ],
  "settings": {
    "autoStart": true
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 唯一标识（uuid） |
| `text` | string | 任务文字 |
| `time` | string | 计划时间 "HH:MM"，可为空 |
| `date` | string | 创建日期 "YYYY-MM-DD" |
| `done` | bool | 是否完成 |
| `completedAt` | string/null | 完成时间，用于"今日已完成"判定 |
| `settings.autoStart` | bool | 开机自启开关 |
| `settings.textColor` | string | 任务区文字颜色 "#RRGGBB"，空串表示用内置默认（暖棕） |

---

## 6. 非功能需求（NFR）

| ID | 需求 |
| --- | --- |
| NFR-1 | 性能：展开/收起无卡顿；启动到胶囊出现 ≤ 3s（含 PyInstaller 解包） |
| NFR-2 | 兼容：Windows 10/11，高分屏缩放正常 |
| NFR-3 | 交付物：PyInstaller 单文件 exe（`--onefile --noconsole`，体积 30～80MB） |
| NFR-4 | 隐私：纯本地运行，无任何网络请求 |
| NFR-5 | 稳定性：仅允许单实例运行，重复启动自动聚焦已有实例 |

---

## 7. 异常与边界

| 场景 | 处理 |
| --- | --- |
| `data.json` 损坏 | 备份为 `.bak`，重建空数据，提示用户 |
| exe 目录不可写 | 保存失败时弹提示，不静默丢失 |
| 跨天（零点前后运行中） | 视图按日期刷新，未完成任务自动进入当日视图 |
| 系统未启用自启写入权限 | 开关置灰并提示 |
| 多实例启动 | 以进程锁/命名互斥体阻止，聚焦已有实例 |

---

## 8. 验收标准（AC）

- 双击 exe 启动，胶囊出现在右边缘且置顶
- 点击胶囊展开面板，顶部显示当天日期+星期；点外部收起
- 新增任务（带/不带时间）出现在列表，重启后仍在
- 勾选任务后划线置灰沉底；重启后状态保持
- 双击任务可改文字与时间；删除按钮可移除任务
- 前一天未完成任务，次日启动仍显示在今日视图
- 开启自启后注册表出现对应项，关闭后移除
- 修改 `data.json` 为非法 JSON 后启动，程序不崩溃且自动重建
- 打包后的 exe 在未安装 Python 的 Windows 电脑上可运行

---

## 9. 里程碑

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| M1 核心骨架 | 置顶无边框窗口 + 胶囊/面板切换 + 日期头部 + 增删勾 + JSON 读写 | AC 前 5 条 |
| M2 完整功能 | 双击编辑 + 顺延逻辑 + 自启开关 + 损坏容错 + 单实例 | AC 全部 |
| M3 打包交付 | PyInstaller 打包、未装 Python 环境实测 | AC 最后 1 条 |

---

## 10. 风险与待确认

| 项 | 说明 | 处理 |
| --- | --- | --- |
| 透明圆角 | Tkinter 对圆角/透明支持有限（需 `transparentcolor`），视觉效果可能偏"方形胶囊" | 先实现功能，视觉后调 |
| 置顶遮挡 | 置顶窗口可能盖住全屏应用 | 本期接受，后续可加"游戏模式"开关 |
| 打包体积 | Python 打包 30～80MB 偏大 | 已接受；后续可评估 Tauri 替代 |
| ① 删除是不要二次确认；② 新增任务时时间不是必填 | 默认：不确认、时间可选 |

模块架构图（与上轮交互图互补，展示分层）：

```
<html style="margin:0;padding:0;">
<div style="background-color:transparent;box-sizing:border-box;">
  <div style="font-size:15px;font-weight:600;color:#1A1B1C;margin-bottom:4px;">PRD 配套 · 模块架构图</div>
  <div style="font-size:12px;color:#6B7280;margin-bottom:16px;">分层架构示意（Tkinter 实现），非真实界面截图。</div>

  <div style="background-color:#FFFFFF;border:1px solid rgba(0,0,0,0.08);border-radius:14px;padding:12px;">
    <div style="font-size:12px;font-weight:600;color:#3E6FA8;margin-bottom:8px;">交互层 · UI（置顶无边框窗口）</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;">
      <div style="flex:1 1 150px;min-width:0;padding:10px 12px;border-radius:10px;background:rgba(139,200,234,0.12);font-size:12px;color:#1A1B1C;">悬浮胶囊<br/><span style="color:#6B7280;font-size:11px;">折叠态 · 仅图标</span></div>
      <div style="flex:1 1 150px;min-width:0;padding:10px 12px;border-radius:10px;background:rgba(139,200,234,0.12);font-size:12px;color:#1A1B1C;">任务面板<br/><span style="color:#6B7280;font-size:11px;">日期头部 + 任务列表</span></div>
      <div style="flex:1 1 150px;min-width:0;padding:10px 12px;border-radius:10px;background:rgba(139,200,234,0.12);font-size:12px;color:#1A1B1C;">设置面板<br/><span style="color:#6B7280;font-size:11px;">开机自启开关</span></div>
    </div>
  </div>

  <div style="text-align:center;font-size:12px;color:#6B7280;margin:6px 0;">▲ 用户操作（点击 / 勾选 / 输入）　▼ 渲染更新</div>

  <div style="background-color:#FFFFFF;border:1px solid rgba(0,0,0,0.08);border-radius:14px;padding:12px;">
    <div style="font-size:12px;font-weight:600;color:#3E6FA8;margin-bottom:8px;">业务层 · 逻辑</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;">
      <div style="flex:1 1 150px;min-width:0;padding:10px 12px;border-radius:10px;background:rgba(26,27,28,0.03);font-size:12px;color:#1A1B1C;">今日视图组装<br/><span style="color:#6B7280;font-size:11px;">未完成顺延 + 今日完成归档</span></div>
      <div style="flex:1 1 150px;min-width:0;padding:10px 12px;border-radius:10px;background:rgba(26,27,28,0.03);font-size:12px;color:#1A1B1C;">任务操作<br/><span style="color:#6B7280;font-size:11px;">新增 / 删除 / 勾选 / 编辑</span></div>
      <div style="flex:1 1 150px;min-width:0;padding:10px 12px;border-radius:10px;background:rgba(26,27,28,0.03);font-size:12px;color:#1A1B1C;">自启管理<br/><span style="color:#6B7280;font-size:11px;">写入 / 移除注册表项</span></div>
    </div>
  </div>

  <div style="text-align:center;font-size:12px;color:#6B7280;margin:6px 0;">▼ 读取 / 写入（变更即落盘）</div>

  <div style="background-color:#FFFFFF;border:1px solid rgba(0,0,0,0.08);border-radius:14px;padding:12px;">
    <div style="font-size:12px;font-weight:600;color:#3E6FA8;margin-bottom:8px;">数据层 · 持久化</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;">
      <div style="flex:1 1 220px;min-width:0;padding:10px 12px;border-radius:10px;background:linear-gradient(135deg, rgba(139,200,234,0.15), rgba(139,200,234,0.30));font-size:12px;color:#1A1B1C;">data.json（与 exe 同目录）<br/><span style="color:#6B7280;font-size:11px;">tasks[] + settings{} · 损坏容错 · 备份重建</span></div>
    </div>
  </div>

  <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">
    <div style="flex:1 1 260px;min-width:0;padding:8px 12px;border-radius:10px;background:rgba(26,27,28,0.02);border:1px dashed rgba(0,0,0,0.12);font-size:12px;color:#6B7280;">系统集成：Windows 注册表 Run 键（开机自启）· 单实例互斥</div>
  </div>
</div>
</html>
```

PRD 共 10 章：背景目标、用户场景、产品概述、功能需求（15 条 FR）、数据模型、非功能需求、异常边界、验收标准（9 条）、里程碑（3 阶段）、风险待确认。

有两点等你拍板（第 10 章末尾）：**删除是否要二次确认**、**新增时时间是否必填**。确认后我就按 PRD 开工写代码。