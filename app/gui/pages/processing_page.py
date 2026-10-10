"""Processing page: body selection, robustness, smoothing and coordinate frame."""

from __future__ import annotations

from ...i18n import tr

import logging
from typing import Optional

from PySide2.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...config import parse_id_list
from ...core.transform import describe_transform
from ..context import AppContext
from ..widgets.cards import HintLabel, SectionBox
from ..widgets.forms import FieldDef, FormBuilder

log = logging.getLogger("nokov.gui.processing")

def selection_fields():
    return [
        FieldDef("min_body_id", tr("最小刚体 ID"), "int", -1, 100000,
                 tooltip=tr("小于该 ID 的刚体不广播。原脚本使用 ID >= 0，因此默认 0（若要排除 ID 0 请填 1）")),
        FieldDef("max_body_id", tr("最大刚体 ID"), "int", -1, 100000,
                 tooltip=tr("大于该 ID 的刚体不广播")),
        FieldDef("include_ids", tr("仅广播这些 ID"), "ids", grow=True,
                 placeholder=tr("例如 1,2,5-8（留空 = 全部）"),
                 tooltip=tr("白名单，优先级高于范围与黑名单")),
        FieldDef("exclude_ids", tr("排除这些 ID"), "ids", grow=True,
                 placeholder=tr("例如 3,4")),
        FieldDef("require_markers", tr("要求至少有标记点"), "bool"),
        FieldDef("min_markers", tr("最少标记点数"), "int", 1, 64,
                 tooltip=tr("用于剔除标记点被遮挡、位姿不可信的刚体")),
    ]

def robustness_fields():
    return [
        FieldDef("abnormal_threshold_mm", tr("异常值阈值"), "float", 0.0, 1000000.0, decimals=0,
                 suffix=" mm", step=1000.0,
                 tooltip=tr("坐标绝对值超过该值的采样视为跟踪跳变；填 0 关闭检测。原脚本为 9000 mm")),
        FieldDef("hold_last_valid", tr("异常时保持上一帧有效值"), "bool",
                 tooltip=tr("与原脚本一致：用上一帧的位置与姿态替换跳变数据")),
        FieldDef("max_hold_frames", tr("最多保持帧数"), "int", 0, 100000,
                 tooltip=tr("超过该帧数仍未恢复则停止广播该刚体；0 = 一直保持")),
        FieldDef("keep_lost_bodies", tr("刚体丢失后继续发送最后位姿"), "bool",
                 tooltip=tr("接收端不会因为刚体短暂消失而得到残缺的包结构")),
        FieldDef("velocity_source", tr("速度来源"), "choice", choices=[
            ("auto", tr("自动（优先使用 SDK 扩展数据）")),
            ("sdk", tr("仅使用 SDK 速度/加速度")),
            ("difference", tr("由位置差分计算")),
        ]),
        FieldDef("euler_source", tr("欧拉角来源"), "choice", choices=[
            ("auto", tr("自动（优先使用 SDK 角度）")),
            ("sdk", tr("仅使用 SDK 角度")),
            ("quaternion", tr("由四元数换算 (Z-Y-X)")),
        ]),
    ]

def smoothing_fields():
    return [
        FieldDef("smoothing", tr("平滑方式"), "choice", choices=[
            ("none", tr("不平滑（与原脚本一致）")),
            ("sma", tr("滑动平均 (SMA)")),
            ("median", tr("滑动中值（抑制尖刺）")),
            ("ema", tr("指数平滑 (EMA)")),
            ("one_euro", tr("One-Euro 自适应滤波（推荐）")),
        ]),
        FieldDef("smoothing_window", tr("窗口长度"), "int", 1, 200, suffix=tr(" 帧"),
                 tooltip=tr("SMA / 中值滤波使用")),
        FieldDef("smoothing_alpha", tr("EMA / 姿态平滑系数"), "float", 0.01, 1.0, decimals=3, step=0.05,
                 tooltip=tr("越小越平滑、延迟越大")),
        FieldDef("one_euro_min_cutoff", tr("One-Euro 最小截止频率"), "float", 0.001, 100.0, decimals=3,
                 suffix=" Hz", step=0.5, tooltip=tr("越小越平滑")),
        FieldDef("one_euro_beta", tr("One-Euro 速度系数 β"), "float", 0.0, 5.0, decimals=4, step=0.01,
                 tooltip=tr("越大越能跟随快速运动")),
        FieldDef("smooth_orientation", tr("同时平滑姿态四元数"), "bool"),
    ]

def transform_fields():
    return [
        FieldDef("axis_map", tr("坐标轴映射"), "choice", choices=[
            ("XYZ", tr("XYZ — 不改变")),
            ("ZYX", tr("ZYX — 交换 X 与 Z")),
            ("XZY", tr("XZY — 交换 Y 与 Z")),
            ("YXZ", "YXZ"),
            ("YZX", "YZX"),
            ("ZXY", "ZXY"),
        ], tooltip=tr("输出轴 = 输入轴按此顺序排列，例如 ZYX 表示 out_x = in_z")),
        FieldDef("sign_x", tr("X 轴方向"), "choice", choices=[(1, tr("保持")), (-1, tr("取反"))]),
        FieldDef("sign_y", tr("Y 轴方向"), "choice", choices=[(1, tr("保持")), (-1, tr("取反"))]),
        FieldDef("sign_z", tr("Z 轴方向"), "choice", choices=[(1, tr("保持")), (-1, tr("取反"))]),
        FieldDef("unit_scale", tr("整体缩放"), "float", -1e6, 1e6, decimals=6, step=0.1,
                 tooltip=tr("在毫米→米换算之后再乘的系数")),
        FieldDef("offset_x", tr("X 偏移"), "float", -1e6, 1e6, decimals=4, suffix=" m", step=0.1),
        FieldDef("offset_y", tr("Y 偏移"), "float", -1e6, 1e6, decimals=4, suffix=" m", step=0.1),
        FieldDef("offset_z", tr("Z 偏移"), "float", -1e6, 1e6, decimals=4, suffix=" m", step=0.1),
        FieldDef("yaw_deg", tr("绕 Z 轴旋转"), "float", -360.0, 360.0, decimals=2, suffix=" °",
                 step=15.0, tooltip=tr("同时作用于位置与姿态")),
    ]


class ProcessingPage(QWidget):
    def __init__(self, ctx: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._next_refresh = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        selection_box = SectionBox(tr("刚体选择"), tr("决定哪些刚体参与广播。默认与原脚本一致：广播所有 ID >= 0 的刚体。"))
        self.selection_form = FormBuilder(selection_fields(), columns=1)
        self.selection_form.load(self.ctx.config.filters)
        self.selection_form.changed.connect(self._on_changed)
        selection_box.add(self.selection_form)
        row1.addWidget(selection_box, 1)

        robustness_box = SectionBox(tr("鲁棒性与运动学"), tr("异常值检测、保持策略，以及速度/角度的来源。"))
        self.robustness_form = FormBuilder(robustness_fields(), columns=1)
        self.robustness_form.load(self.ctx.config.filters)
        self.robustness_form.changed.connect(self._on_changed)
        robustness_box.add(self.robustness_form)
        row1.addWidget(robustness_box, 1)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        smoothing_box = SectionBox(tr("平滑滤波"), tr("抑制抖动。默认关闭，以保证与旧程序完全一致。"))
        self.smoothing_form = FormBuilder(smoothing_fields(), columns=1)
        self.smoothing_form.load(self.ctx.config.filters)
        self.smoothing_form.changed.connect(self._on_changed)
        smoothing_box.add(self.smoothing_form)
        reset_button = QPushButton(tr("重置滤波器状态"))
        reset_button.clicked.connect(self._on_reset_filters)
        smoothing_box.add(reset_button)
        row2.addWidget(smoothing_box, 1)

        transform_box = SectionBox(tr("坐标系变换"), tr("在发送前对位置与姿态做整体变换。默认为恒等变换。"))
        self.transform_form = FormBuilder(transform_fields(), columns=1)
        self.transform_form.load(self.ctx.config.transform)
        self.transform_form.changed.connect(self._on_changed)
        transform_box.add(self.transform_form)
        row2.addWidget(transform_box, 1)
        root.addLayout(row2)

        summary_box = SectionBox(tr("当前处理摘要"))
        self.summary_label = HintLabel("")
        summary_box.add(self.summary_label)
        self.stats_label = HintLabel("")
        summary_box.add(self.stats_label)
        root.addWidget(summary_box)
        root.addStretch(1)

        self._update_summary()

    # ------------------------------------------------------------------ #
    def _on_changed(self) -> None:
        self.selection_form.collect(self.ctx.config.filters)
        self.robustness_form.collect(self.ctx.config.filters)
        self.smoothing_form.collect(self.ctx.config.filters)
        self.transform_form.collect(self.ctx.config.transform)
        self.ctx.config_changed()
        self._update_smoothing_enabled()
        self._update_summary()

    def _on_reset_filters(self) -> None:
        self.ctx.engine.reset_pipeline()
        self.ctx.hub.set_body_names(self.ctx.session.info.rigid_bodies)
        self.ctx.engine.pipeline.register_known_bodies(self.ctx.session.info.rigid_bodies)
        self._update_summary(force_text=tr("滤波器与缓存已重置。"))

    # ------------------------------------------------------------------ #
    def _update_smoothing_enabled(self) -> None:
        mode = self.ctx.config.filters.smoothing
        uses_window = mode in ("sma", "median")
        uses_alpha = mode == "ema"
        uses_one_euro = mode == "one_euro"
        self.smoothing_form.set_row_enabled("smoothing_window", uses_window)
        self.smoothing_form.set_row_enabled("smoothing_alpha", uses_alpha or
                                           self.ctx.config.filters.smooth_orientation)
        self.smoothing_form.set_row_enabled("one_euro_min_cutoff", uses_one_euro)
        self.smoothing_form.set_row_enabled("one_euro_beta", uses_one_euro)

    def _update_summary(self, force_text: str = "") -> None:
        filters = self.ctx.config.filters
        pipeline = self.ctx.engine.pipeline
        parts = [
            tr("刚体选择：%s") % pipeline.selector.describe(),
            tr("异常阈值：%s") % (tr("关闭") if filters.abnormal_threshold_mm <= 0
                             else "%.0f mm" % filters.abnormal_threshold_mm),
            tr("异常处理：%s") % (tr("保持上一帧") if filters.hold_last_valid else tr("直接透传")),
            tr("平滑：%s") % {
                "none": tr("关闭"), "sma": tr("滑动平均(%d)") % filters.smoothing_window,
                "median": tr("中值(%d)") % filters.smoothing_window,
                "ema": tr("指数(α=%.3f)") % filters.smoothing_alpha,
                "one_euro": "One-Euro(%.3f Hz, β=%.4f)"
                            % (filters.one_euro_min_cutoff, filters.one_euro_beta),
            }.get(filters.smoothing, filters.smoothing),
            tr("坐标系：%s") % describe_transform(self.ctx.config.transform),
        ]
        if force_text:
            parts.insert(0, force_text)
        self.summary_label.setText("　|　".join(parts))

        stats = self.ctx.engine.pipeline.stats
        self.stats_label.setText(
            tr("累计处理 %d 帧；检出异常 %d 次，保持 %d 次，被过滤丢弃 %d 次，"
            "当前参与广播的刚体 %d 个")
            % (stats.frames_in, stats.glitches, stats.held,
               stats.dropped_by_filter, stats.bodies_out)
        )

        include = parse_id_list(filters.include_ids)
        if filters.include_ids and not include:
            self.summary_label.setText(tr("“仅广播这些 ID”内容无法解析，请检查格式。"))

    # ------------------------------------------------------------------ #
    def reload_from_config(self) -> None:
        self.selection_form.load(self.ctx.config.filters)
        self.robustness_form.load(self.ctx.config.filters)
        self.smoothing_form.load(self.ctx.config.filters)
        self.transform_form.load(self.ctx.config.transform)
        self._update_smoothing_enabled()
        self._update_summary()

    def refresh(self, now: float) -> None:
        if now < self._next_refresh:
            return
        self._next_refresh = now + 0.5
        self._update_summary()
        self._update_smoothing_enabled()
