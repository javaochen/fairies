import sys
import math
import random
from dataclasses import dataclass
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QCursor, QLinearGradient
from PyQt6.QtWidgets import QApplication, QWidget


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def smoothstep(edge0, edge1, x):
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass
class Fairy:
    color: QColor
    pos: QPointF
    vel: QPointF
    scale: float
    phase: float
    visible: bool = True
    hidden_timer: int = 0
    shape_seed: float = 0.0
    hide_chance: float = 0.0018
    trail: list = None

    bounce_vx: float = 0.0
    bounce_vy: float = 0.0
    bounce_timer: int = 0

    def __post_init__(self):
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

    def maybe_bounce(self, mouse: QPointF, t: float, R1: float):
        if int(t) % 60 != 0:
            return

        dx = mouse.x() - self.pos.x()
        dy = mouse.y() - self.pos.y()
        dist = math.hypot(dx, dy) + 1e-6

        if dist <= R1:
            p = 1.0
        else:
            p = clamp(math.exp(-(dist - R1) / 90.0), 0.03, 0.95)

        if random.random() < p:
            ang = random.random() * math.tau
            jump = random.uniform(160.0, 360.0)
            self.bounce_vx = math.cos(ang) * jump
            self.bounce_vy = math.sin(ang) * jump
            self.bounce_timer = random.randint(10, 22)

    def mouse_force(self, distm: float, R1: float, R2: float):
        # R1~R2 鼠标主导；>R2 明显弱化
        if distm <= R1:
            return 0.0
        if distm <= R2:
            # 在 R1~R2 之间，靠近 R1 最强，靠近 R2 逐步变弱
            s = 1.0 - smoothstep(R1, R2, distm)
            return 3.2 * s + 0.55
        # >R2 后保留一点鼠标吸引，但明显弱
        return 0.22 + 0.18 * math.exp(-(distm - R2) / 240.0)

    def fairy_force(self, disto: float, R2: float):
        # 不用反比公式：采用“缓慢衰减的平滑吸引”
        # 在 R2 外仍保持明显吸引，不会衰减太快
        # 这里是一个“宽平台 + 平滑衰减”
        if disto <= 12.0:
            return 0.0

        # 以 160~520 的范围做宽缓衰减
        base = 2.4
        mid = 260.0
        width = 180.0

        # 距离越大，靠 smoothstep 缓慢减弱，但不会太快归零
        s = 1.0 - smoothstep(mid - width, mid + width, disto)
        # 额外留底，确保 >R2 时仍明显
        return base * (0.35 + 0.65 * s)

    def update(self, mouse: QPointF, other: "Fairy", screen_w: int, screen_h: int, t: float, R1: float, R2: float):
        self.maybe_toggle_visibility()
        self.maybe_bounce(mouse, t, R1)

        if not self.visible:
            if self.trail:
                self.trail.pop(0)
            return

        dxm = mouse.x() - self.pos.x()
        dym = mouse.y() - self.pos.y()
        distm = math.hypot(dxm, dym) + 1e-6

        dxo = other.pos.x() - self.pos.x()
        dyo = other.pos.y() - self.pos.y()
        disto = math.hypot(dxo, dyo) + 1e-6

        # 鼠标吸引
        mf = self.mouse_force(distm, R1, R2)
        axm = dxm / distm * mf
        aym = dym / distm * mf

        # 精灵间吸引：更明显、衰减更慢
        ff = self.fairy_force(disto, R2)
        axo = dxo / disto * ff
        ayo = dyo / disto * ff

        # 权重分区
        if distm > R2:
            ax = axo * 2.6 + axm * 0.45
            ay = ayo * 2.6 + aym * 0.45
        else:
            ax = axm * 1.9 + axo * 0.85
            ay = aym * 1.9 + ayo * 0.85

        wobble_x = math.sin(t * 0.03 + self.phase) * 0.14 + random.uniform(-0.04, 0.04)
        wobble_y = math.cos(t * 0.028 + self.phase * 1.3) * 0.14 + random.uniform(-0.04, 0.04)

        self.vel = QPointF(
            self.vel.x() * 0.80 + ax + wobble_x,
            self.vel.y() * 0.80 + ay + wobble_y
        )

        if self.bounce_timer > 0:
            strength = self.bounce_timer / 22.0
            self.vel = QPointF(
                self.vel.x() + self.bounce_vx * 0.10 * strength,
                self.vel.y() + self.bounce_vy * 0.10 * strength
            )
            self.bounce_timer -= 1
            self.bounce_vx *= 0.92
            self.bounce_vy *= 0.92

        # 速度上界
        max_speed = 120.0
        sp = math.hypot(self.vel.x(), self.vel.y())
        if sp > max_speed:
            s = max_speed / sp
            self.vel = QPointF(self.vel.x() * s, self.vel.y() * s)

        self.pos += self.vel

        # 边界回拉
        margin = 6.0
        if self.pos.x() < margin:
            self.pos.setX(margin)
            self.vel = QPointF(abs(self.vel.x()) * 0.55, self.vel.y())
        elif self.pos.x() > screen_w - margin:
            self.pos.setX(screen_w - margin)
            self.vel = QPointF(-abs(self.vel.x()) * 0.55, self.vel.y())

        if self.pos.y() < margin:
            self.pos.setY(margin)
            self.vel = QPointF(self.vel.x(), abs(self.vel.y()) * 0.55)
        elif self.pos.y() > screen_h - margin:
            self.pos.setY(screen_h - margin)
            self.vel = QPointF(self.vel.x(), -abs(self.vel.y()) * 0.55)

        self.trail.append(QPointF(self.pos))
        if len(self.trail) > 18:
            self.trail.pop(0)

        self.scale += math.sin(t * 0.05 + self.shape_seed) * 0.0015
        self.scale = clamp(self.scale, 0.72, 1.25)


class Overlay(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Tiny Fairy Meteors Force Field v2")
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
        self.R1 = 18.0
        self.R2 = 120.0

        self.fairies = [
            Fairy(
                color=QColor(255, 90, 210),
                pos=QPointF(random.randint(100, 500), random.randint(100, 500)),
                vel=QPointF(0.0, 0.0),
                scale=1.0,
                phase=random.random() * math.tau,
                shape_seed=random.random() * 1000,
                hide_chance=0.0014
            ),
            Fairy(
                color=QColor(80, 220, 255),
                pos=QPointF(random.randint(200, 700), random.randint(150, 600)),
                vel=QPointF(0.0, 0.0),
                scale=0.92,
                phase=random.random() * math.tau,
                shape_seed=random.random() * 1000,
                hide_chance=0.0018
            )
        ]

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def tick(self):
        self.t += 1.0
        mouse = QCursor.pos()
        m = QPointF(mouse.x(), mouse.y())

        for i, fairy in enumerate(self.fairies):
            fairy.update(m, self.fairies[1 - i], self.screen_w, self.screen_h, self.t, self.R1, self.R2)

        self.update()

    def draw_trail(self, painter: QPainter, fairy: Fairy):
        if len(fairy.trail) < 2:
            return
        n = len(fairy.trail)
        for i, pt in enumerate(fairy.trail):
            k = i / max(1, n - 1)
            alpha = int(10 + 65 * k)
            c = QColor(fairy.color)
            c.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            r = 0.5 + 1.6 * k * fairy.scale
            painter.drawEllipse(pt, r, r)

    def draw_fairy(self, painter: QPainter, fairy: Fairy):
        self.draw_trail(painter, fairy)

        if not fairy.visible:
            return

        x = fairy.pos.x()
        y = fairy.pos.y()

        body_r = 1.5 * fairy.scale
        halo_r = 2.8 * fairy.scale

        grad = QLinearGradient(x - 3, y - 3, x + 3, y + 3)
        grad.setColorAt(0.00, QColor(255, 90, 210))
        grad.setColorAt(0.33, QColor(90, 220, 255))
        grad.setColorAt(0.66, QColor(255, 220, 120))
        grad.setColorAt(1.00, QColor(180, 120, 255))

        painter.setPen(QPen(grad, 0.40))
        painter.setBrush(QColor(255, 255, 255, 248))
        painter.drawEllipse(QPointF(x, y), body_r, body_r)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawEllipse(QPointF(x, y), 0.85 * fairy.scale, 0.85 * fairy.scale)

        painter.setBrush(QColor(255, 255, 255, 24))
        painter.drawEllipse(QPointF(x, y), halo_r, halo_r)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for fairy in self.fairies:
            self.draw_fairy(painter, fairy)


def main():
    app = QApplication(sys.argv)
    w = Overlay()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()