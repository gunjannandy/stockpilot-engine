"""The chance model: a smoothed bucket base rate, a regularised logistic regression, their blend in log-odds, and a Platt
calibration. Plain numpy so it runs anywhere the history runs. See docs/research/forecast-v2.md section 3."""
from dataclasses import dataclass

import numpy as np

CLIP = (0.15, 0.85)


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def smoothed_rate(hits: float, n: float, parent: float, overlap: float, k: float = 30.0) -> float:
    """Beta-style shrink to the parent rate; the sample counts as n / overlap because neighbouring start days share outcomes."""
    n_eff = n / max(overlap, 1.0)
    return (hits / max(overlap, 1.0) + k * parent) / (n_eff + k)


def _newton(z, y, pen, prior, steps=60):
    """Penalised logistic loss by Newton steps with step halving, so a long first step cannot overshoot."""
    def loss(w):
        zw = z @ w
        return np.sum(np.logaddexp(0, zw) - y * zw) + 0.5 * (w - prior) @ pen @ (w - prior)
    w = prior.copy()
    cur = loss(w)
    for _ in range(steps):
        q = sigmoid(z @ w)
        grad = z.T @ (q - y) + pen @ (w - prior)
        hess = (z * (q * (1 - q))[:, None]).T @ z + pen + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(hess, grad)
        scale = 1.0
        while scale > 1e-6 and loss(w - scale * step) > cur:
            scale /= 2
        w = w - scale * step
        new = loss(w)
        done = cur - new < 1e-10 * max(1.0, abs(cur))
        cur = new
        if done:
            break
    return w


@dataclass
class Logistic:
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray        # per standardised feature
    bias: float

    def score(self, x):
        return ((x - self.mean) / self.scale) @ self.coef + self.bias

    def predict(self, x):
        return sigmoid(self.score(x))


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0) -> Logistic:
    """L2-penalised logistic regression by Newton steps on standardised inputs. The bias is not penalised."""
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale < 1e-12, 1.0, scale)
    z = np.hstack([(x - mean) / scale, np.ones((len(x), 1))])
    pen = np.eye(z.shape[1]) * l2
    pen[-1, -1] = 0
    w = _newton(z, y, pen, np.zeros(z.shape[1]))
    return Logistic(mean, scale, w[:-1], float(w[-1]))


def blend(base: np.ndarray, logistic: np.ndarray) -> np.ndarray:
    """Equal-weight average of the two chances in log-odds, clipped to 15%-85%."""
    return np.clip(sigmoid((logit(base) + logit(logistic)) / 2), *CLIP)


@dataclass
class Platt:
    a: float
    b: float

    def apply(self, p):
        return np.clip(sigmoid(self.a * logit(p) + self.b), *CLIP)


def fit_platt(p: np.ndarray, y: np.ndarray) -> Platt:
    """Sigmoid calibration: y ~ sigmoid(a * logit(p) + b), a light ridge keeps a and b steady on small samples."""
    z = np.column_stack([logit(p), np.ones(len(p))])
    w = _newton(z, y, np.diag([1e-3, 1e-3]), np.array([1.0, 0.0]))
    a = max(float(w[0]), 0.05)         # never flip the order of the scores
    return Platt(a, float(w[1]))
