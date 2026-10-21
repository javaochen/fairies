import sys
import math
import random
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QCursor, QLinearGradient, QFont
from PyQt6.QtWidgets import QApplication, QWidget


# “好像来自天堂”


#  参数调优速查  (fairy_kuramoto.py)
# -----------------------------------------------------------------------------
#  核心架构：节点坐标 = 相对群体中心的位置，角度完全由 Kuramoto 相位 θ 决定；
#           鼠标只作用于 group_center（整团被“搬运”），不逐个扰动节点。
#  因此：同步/失步（序参量 R）只由 θ 动力学决定，与“半径/位置”无关——
#       半径仅仅改变这些相位的“空间呈现”大小。
#  下面按区块列出主要可调旋钮（含默认值与效果）。改完直接运行即可。
# =============================================================================
#
#  【A. 群体几何】  (__init__ 中)
#   min_group_radius / unit_radius  (默认 120)
#       · 节点环半径。大→展开明显、线速度高、同步/失步在画面上最醒目；
#         小→紧凑平静，但相位差空间上不易辨别（<15 时几乎成一个点）。
#       · 建议范围 100–150。unit_radius 仅用于初始摆位。
#   目标半径呼吸幅度  (tick 中 r = min_group_radius + 16.0*sin(...))
#       · 呼吸脉动幅度。注意 16.0 若大于 min_group_radius，下半段会被
#         max(min_group_radius, r) 夹断，变成单向起伏。
#
#  【B. Kuramoto 动力学】  (决定 R 的摆动)
#   omegas 列表  (默认 [0.6, 1.15, 1.45, 1.9, 2.4])
#       · 各节点“自然频率”。差越大越容易失步、相变越明显；
#         全相近则瞬间锁相、看不到过程。
#   K_base / K_amp  (__init__ 默认 8.0 / 14.0)
#       · 耦合 K = K_base + K_amp * sin(t * ωm)。
#       · 等效耦合 K_eff = K / N，临界约 Kc≈1.15（当前频率分布下）。
#         想让 R 明显下探，需让 K 深潜到 ~0 甚至负值（加大 K_amp、降低 K_base）。
#   调制角频率 0.007  (tick 中 sin(self.t * 0.007))
#       · 越小周期越长（现约 15s）。想更慢改 0.005，更快改 0.009。
#   相位噪声  random.uniform(-0.5, 0.5)  (tick 中)
#       · 越大越易散开；想更“纯净锁相”可减小。
#
#  【B2. 网络耦合 / 邻接矩阵】  (__init__ 参数)
#   adjacency (默认 None = 随机图) / connectivity (默认 0.6)
#   reshuffle (默认 True) / reshuffle_period (默认 900 tick ≈ 一个 K 周期 ≈15s)
#       · 传入 N×N 权重矩阵（对称、对角线为 0）则按该网络耦合各节点；给定矩阵时
#         永不重洗（忽略 reshuffle），拓扑固定。
#       · 为 None（随机）时按 connectivity 概率生成随机图；且默认每过
#         reshuffle_period 重洗一次邻接矩阵（“每轮切换”），重洗不打印、仅由
#         draw_network 反映新拓扑。设 reshuffle=False 可关闭自动重洗。
#       · 耦合按节点度数归一：θ_i' = ω_i + (K/deg_i) Σ_j A_ij sin(θ_j-θ_i)，
#         度数越高越易保持同步；孤立节点(deg=0)只随自身频率。
#       · HUD 额外显示边数 E，便于观察随机重洗后的拓扑变化。
#       · 用法示例：Overlay(adjacency=[[0,1,0],[1,0,1],[0,1,0]])   # 固定拓扑
#                  Overlay()                                      # 随机+每轮重洗
#                  Overlay(connectivity=0.4, reshuffle_period=600) # 更稀疏、更快重洗
#
#  【C. 鼠标交互（仅作用于中心）】
#   R1 / R2  (__init__ 默认 30.0 / 230.0)
#       · 中心受排斥的内半径(强)/外半径(柔和衰减，外无作用)。
#       · R2 应 ≥ 种群半径(min_group_radius)，否则最外圈节点会停在光标下
#         而中心不躲（因为鼠标只推中心）。种群变大时记得同步调大 R2。
#   避让推力系数 12.0、max_group_speed 7.0  (tick 中 group_center)
#       · 中心逃离的强度与速度上限。
#
#  【D. 节点运动】
#   spring_k 0.30  (tick 中)
#       · 跟随“相位目标”的弹簧刚度，越大贴得越紧、延迟越小。
#   max_speed 90.0  (tick 中)
#       · 节点线速度上限；半径越大越容易顶到。
#
#  【E. 可视化】
#   序参量指针  length = 22.0 + R*80.0、edge 色(120,230,255,180)、
#               core 宽 2.0+4.0*R、head 环 1.2  (draw_dynamics 中)
#       · 方向=平均相位 Ψ，长度/亮度=相干度 R。改这些可调指针观感。
#   参考环 alpha 28、辐条 alpha 55  (draw_dynamics 中)
#   拖尾长度  (trail 上限 32)、缩放脉动幅度 0.0015  (tick 中)
#
#  【F. 帧率】
#   timer.start(16) 与 dt = 1.0/60.0  (tick 中)
#       · 约 60fps。若改帧间隔，dt 需同步改，否则动力学速度会变。
#
#  常用调参组合：
#   · 想“聚散更剧烈”：K_base→6, K_amp→16
#   · 想“周期更长”：0.007→0.005
#   · 想“画面更舒展”：min_group_radius→150, R2→230(已覆盖)
#   · 想“更紧凑平静”：min_group_radius→60
# =============================================================================


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def smoothstep(edge0, edge1, x):
    t = clamp((x - edge0) / (edge1 - edge0 + 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mouse_force(distm: float, R1: float, R2: float):
    """
    鼠标力模型（来自 fairy4）：
    1) R1 内：强排斥（越靠近越强）
    2) R1~R2：柔和排斥衰减
    3) R2 外：无鼠标力
    返回标量强度，方向在调用处统一处理（<0 表示排斥）
    """
    if distm <= R1:
        k = 1.0 - distm / (R1 + 1e-6)        # 0..1
        return -(6.5 + 11.0 * (k * k))        # 约 -6.5 ~ -17.5
    if distm <= R2:
        s = 1.0 - smoothstep(R1, R2, distm)   # 近强远弱
        return -(1.2 + 4.2 * s)               # 约 -1.2 ~ -5.4
    return 0.0


@dataclass
class KuramotoUnit:
    color: QColor
    theta: float
    omega: float
    phase_offset: float
    pos: QPointF = None
    vel: QPointF = None
    trail: list = None
    scale: float = 1.0

    # --- 渲染/鲜活相关字段（不影响 Kuramoto 编队）---
    phase: float = 0.0
    visible: bool = True
    hidden_timer: int = 0
    shape_seed: float = 0.0
    hide_chance: float = 0.0018

    def __post_init__(self):
        if self.pos is None:
            self.pos = QPointF(0.0, 0.0)
        if self.vel is None:
            self.vel = QPointF(0.0, 0.0)
        if self.trail is None:
            self.trail = []

    def maybe_toggle_visibility(self):
        if self.hidden_timer > 0:
            self.hidden_timer -= 1
            if self.hidden_timer <= 0:
                self.visible = True
            return
        if random.random() < self.hide_chance:
            self.visible = False
            self.hidden_timer = random.randint(14, 42)

class Overlay(QWidget):
    def __init__(self, adjacency=None, connectivity=0.6, reshuffle=True, reshuffle_period=900):
        super().__init__()

        self.setWindowTitle("Kuramoto Fairies v2")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        screen = QApplication.primaryScreen().geometry()
        self.screen_w = screen.width()
        self.screen_h = screen.height()
        self.setGeometry(screen)

        self.t = 0.0

        # 鼠标作用在整个群体中心（半径 150 的种群），分区需覆盖种群范围
        self.R1 = 30.0
        self.R2 = 230.0

        # Kuramoto 耦合大幅越过临界：K 深潜到 0 附近/负值以彻底失步，周期更长让散开充分发育
        self.K_base = -1.1
        self.K_amp = 14.0

        # HUD 字体
        self.hud_font = QFont("Consolas", 13)

        self.center = QPointF(self.screen_w * 0.5, self.screen_h * 0.5)
        self.group_center = QPointF(self.center.x(), self.center.y())
        self.group_vel = QPointF(0.0, 0.0)

        self.min_group_radius = 120.0
        self.unit_radius = 120.0

        colors = [
            QColor(255, 90, 210),
            QColor(80, 220, 255),
            QColor(255, 220, 120),
            QColor(180, 120, 255),
            QColor(120, 255, 160),
        ]

        # 拉开自然频率差，使 Kuramoto 同步相变可见
        omegas = [0.6, 1.15, 1.45, 1.9, 2.4]
        self.units = []
        for i in range(5):
            ang = i * (math.tau / 5.0)
            self.units.append(
                KuramotoUnit(
                    color=colors[i],
                    theta=ang + 0.2 * i,
                    omega=omegas[i],
                    phase_offset=ang,
                    phase=random.random() * math.tau,
                    shape_seed=random.random() * 1000,
                    hide_chance=random.choice([0.0012, 0.0016, 0.0020]),
                    pos=QPointF(
                        self.center.x() + self.unit_radius * math.cos(ang),
                        self.center.y() + self.unit_radius * math.sin(ang)
                    )
                )
            )

        # --- 邻接矩阵 / 随机图 ---
        # adjacency: 显式 N×N 权重矩阵(对称、对角线为 0)；为 None 时按 connectivity
        #            概率生成随机图(Erdős–Rényi)。矩阵不打印，仅可视化存在的细连线。
        # 随机模式默认“每轮”重洗邻接矩阵(reshuffle=True)；给定矩阵时永不重洗。
        n = len(self.units)
        self.adjacency_given = adjacency is not None
        self.connectivity = connectivity
        self.reshuffle = reshuffle
        self.reshuffle_period = reshuffle_period   # 单位：tick(≈16ms)，默认约一个 K 周期
        self._last_reshuffle = 0.0
        if self.adjacency_given:
            self.adj = [[float(v) for v in row] for row in adjacency]
        else:
            self.adj = self._build_random_adj(n)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def _build_random_adj(self, n):
        adj = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                if random.random() < self.connectivity:
                    adj[i][j] = 1.0
                    adj[j][i] = 1.0
        return adj

    def tick(self):
        dt = 1.0 / 60.0
        self.t += 1.0
        mouse = QCursor.pos()
        m = QPointF(mouse.x(), mouse.y())

        # --- phase update (Kuramoto 网络耦合)，K 在临界值附近缓慢调制 ---
        K = self.K_base + self.K_amp * math.sin(self.t * 0.003)
        self.cur_K = K

        # 随机模式：每过 reshuffle_period 重洗邻接矩阵（给定矩阵时 self.adjacency_given 为
        # True，永不触发）。不打印，下一帧 draw_network 即反映新拓扑。
        if self.reshuffle and not self.adjacency_given:
            if self.t - self._last_reshuffle >= self.reshuffle_period:
                self.adj = self._build_random_adj(len(self.units))
                self._last_reshuffle = self.t

        for i, unit in enumerate(self.units):
            coupling = 0.0
            deg = 0.0
            for j, other in enumerate(self.units):
                if i == j:
                    continue
                w = self.adj[i][j]
                if w != 0.0:
                    coupling += w * math.sin(other.theta - unit.theta)
                    deg += abs(w)

            noise = random.uniform(-0.5, 0.5)
            if deg > 0:
                # 按节点度数归一：度数越高越易保持同步；孤立节点只随自身频率
                unit.theta += dt * (unit.omega + (K / deg) * coupling + noise)
            else:
                unit.theta += dt * (unit.omega + noise)

        # 序参量：复相位均值 R（相干度 0..1）与 Ψ（平均相位）
        zx = 0.0
        zy = 0.0
        for unit in self.units:
            zx += math.cos(unit.theta)
            zy += math.sin(unit.theta)
        n = len(self.units)
        self.order_R = math.hypot(zx, zy) / n
        self.order_psi = math.atan2(zy, zx)

        # --- group center：采用 fairy4 的强排斥鼠标模型 ---
        dx = self.group_center.x() - m.x()
        dy = self.group_center.y() - m.y()
        dist = math.hypot(dx, dy) + 1e-6

        mf = mouse_force(dist, self.R1, self.R2)
        if dist < self.R2:
            # mf<0 => 排斥；远离鼠标方向 = (dx,dy)/dist
            ax = dx / dist * (-mf) * 12.0
            ay = dy / dist * (-mf) * 12.0
        else:
            ax = 0.0
            ay = 0.0

        ax += random.uniform(-0.4, 0.4)
        ay += random.uniform(-0.4, 0.4)

        self.group_vel = QPointF(
            self.group_vel.x() * 0.88 + ax * dt,
            self.group_vel.y() * 0.88 + ay * dt
        )

        max_group_speed = 7.0
        gsp = math.hypot(self.group_vel.x(), self.group_vel.y())
        if gsp > max_group_speed:
            s = max_group_speed / gsp
            self.group_vel = QPointF(self.group_vel.x() * s, self.group_vel.y() * s)

        self.group_center += self.group_vel

        margin = 20.0
        if self.group_center.x() < margin:
            self.group_center.setX(margin)
            self.group_vel = QPointF(abs(self.group_vel.x()) * 0.4, self.group_vel.y())
        elif self.group_center.x() > self.screen_w - margin:
            self.group_center.setX(self.screen_w - margin)
            self.group_vel = QPointF(-abs(self.group_vel.x()) * 0.4, self.group_vel.y())

        if self.group_center.y() < margin:
            self.group_center.setY(margin)
            self.group_vel = QPointF(self.group_vel.x(), abs(self.group_vel.y()) * 0.4)
        elif self.group_center.y() > self.screen_h - margin:
            self.group_center.setY(self.screen_h - margin)
            self.group_vel = QPointF(self.group_vel.x(), -abs(self.group_vel.y()) * 0.4)

        # --- target positions：完全由相位决定（相对中心） ---
        targets = []
        for unit in self.units:
            ang = unit.theta + unit.phase_offset
            # 半径随相位轻微“呼吸”，但完全确定、无随机，保持 Kuramoto 形态
            r = self.min_group_radius + 16.0 * math.sin(unit.theta * 0.6 + unit.phase_offset)
            r = max(self.min_group_radius, r)
            tx = self.group_center.x() + r * math.cos(ang)
            ty = self.group_center.y() + r * math.sin(ang)
            targets.append([tx, ty])

        max_r = 0.0
        for tx, ty in targets:
            max_r = max(max_r, math.hypot(tx - self.group_center.x(), ty - self.group_center.y()))
        if max_r < self.min_group_radius:
            factor = self.min_group_radius / max(max_r, 1e-6)
            for i in range(len(targets)):
                tx, ty = targets[i]
                vx = tx - self.group_center.x()
                vy = ty - self.group_center.y()
                targets[i][0] = self.group_center.x() + vx * factor
                targets[i][1] = self.group_center.y() + vy * factor

        # --- local motion：节点只跟随“相对中心的相位目标” ---
        # 外界交互（鼠标）只作用于 group_center，节点坐标完全由 Kuramoto 相位决定
        for unit, (tx, ty) in zip(self.units, targets):
            unit.maybe_toggle_visibility()

            if not unit.visible:
                if unit.trail:
                    unit.trail.pop(0)
                continue

            # 弹簧指向相位目标（相对中心），让运动平滑、贴合编队
            dx = tx - unit.pos.x()
            dy = ty - unit.pos.y()
            spring_k = 0.30
            unit.vel = QPointF(
                unit.vel.x() * 0.82 + dx * spring_k,
                unit.vel.y() * 0.82 + dy * spring_k
            )

            max_speed = 90.0
            sp = math.hypot(unit.vel.x(), unit.vel.y())
            if sp > max_speed:
                s = max_speed / sp
                unit.vel = QPointF(unit.vel.x() * s, unit.vel.y() * s)

            unit.pos += unit.vel

            unit.trail.append(QPointF(unit.pos))
            if len(unit.trail) > 32:
                unit.trail.pop(0)

            # 基于相位的缩放脉动
            unit.scale += math.sin(self.t * 0.05 + unit.shape_seed) * 0.0015
            unit.scale = clamp(unit.scale, 0.72, 1.25)

        self.update()

    def draw_trail(self, painter: QPainter, unit: KuramotoUnit):
        n = len(unit.trail)
        if n < 2:
            return

        for i, pt in enumerate(unit.trail):
            k = i / max(1, n - 1)
            alpha = int(4 + 100 * k)
            c = QColor(unit.color)
            c.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            r = (0.5 + 1.8 * k) * unit.scale
            painter.drawEllipse(pt, r, r)

    def draw_unit(self, painter: QPainter, unit: KuramotoUnit):
        self.draw_trail(painter, unit)

        if not unit.visible:
            return

        x = unit.pos.x()
        y = unit.pos.y()

        grad = QLinearGradient(x - 6, y - 6, x + 6, y + 6)
        grad.setColorAt(0.00, QColor(255, 90, 210))
        grad.setColorAt(0.25, QColor(80, 220, 255))
        grad.setColorAt(0.50, QColor(255, 220, 120))
        grad.setColorAt(0.75, QColor(180, 120, 255))
        grad.setColorAt(1.00, QColor(120, 255, 160))

        # 柔光晕
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(unit.color.red(), unit.color.green(), unit.color.blue(), 26))
        painter.drawEllipse(QPointF(x, y), 3.4 * unit.scale, 3.4 * unit.scale)

        painter.setPen(QPen(grad, 0.4))
        painter.setBrush(QColor(255, 255, 255, 245))
        painter.drawEllipse(QPointF(x, y), 1.6 * unit.scale, 1.6 * unit.scale)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawEllipse(QPointF(x, y), 0.8 * unit.scale, 0.8 * unit.scale)

    def draw_network(self, painter: QPainter):
        # 邻接矩阵不打印，只把存在的边画成细连线
        n = len(self.units)
        for i in range(n):
            for j in range(i + 1, n):
                if self.adj[i][j] == 0.0:
                    continue
                a = self.units[i]
                b = self.units[j]
                if not a.visible or not b.visible:
                    continue
                painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
                painter.drawLine(a.pos, b.pos)

    def draw_dynamics(self, painter: QPainter):
        cx = self.group_center.x()
        cy = self.group_center.y()

        # 参考环：标出群体半径，便于观察节点在环上的分布
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), self.min_group_radius, self.min_group_radius)

        # 辐条：中心 → 各节点，直观显示每个节点的相位角位置
        for unit in self.units:
            if not unit.visible:
                continue
            painter.setPen(QPen(
                QColor(unit.color.red(), unit.color.green(), unit.color.blue(), 55), 1.0))
            painter.drawLine(QPointF(cx, cy), unit.pos)

        # 序参量指针：方向 = 平均相位 Ψ，长度/亮度 = 相干度 R
        R = getattr(self, "order_R", 0.0)
        Psi = getattr(self, "order_psi", 0.0)
        if R > 0.04:
            length = 22.0 + R * 80.0
            hx = cx + length * math.cos(Psi)
            hy = cy + length * math.sin(Psi)
            col = QColor(255, 255, 255, int(60 + 195 * R))
            core_w = 2.0 + 4.0 * R
            # 极薄有色边缘（青色描边在底层）
            edge = QColor(120, 230, 255, 180)
            painter.setPen(QPen(edge, core_w + 2.0))
            painter.drawLine(QPointF(cx, cy), QPointF(hx, hy))
            # 白色核心
            painter.setPen(QPen(col, core_w))
            painter.drawLine(QPointF(cx, cy), QPointF(hx, hy))
            # 头部：白色填充 + 极薄有色环
            rr = 3.0 * R
            painter.setPen(QPen(edge, 1.2))
            painter.setBrush(col)
            painter.drawEllipse(QPointF(hx, hy), rr, rr)

        # HUD：实时显示相干度 R、当前耦合 K、边数 E（拓扑变化可见）
        painter.setPen(QPen(QColor(255, 255, 255, 210), 1.0))
        painter.setFont(self.hud_font)
        K = getattr(self, "cur_K", 0.0)
        nn = len(self.units)
        ec = sum(1 for a in range(nn) for b in range(a + 1, nn) if self.adj[a][b] != 0.0)
        painter.drawText(16, 28, f"R = {R:.2f}   K = {K:.1f}   E = {ec}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.draw_network(painter)
        self.draw_dynamics(painter)
        for unit in self.units:
            self.draw_unit(painter, unit)


def main():
    app = QApplication(sys.argv)
    w = Overlay()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
