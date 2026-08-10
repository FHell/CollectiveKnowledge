# The heat equation

The temperature $u(x, t)$ of a thin rod evolves according to the heat
equation, $u_t = \alpha\, u_{xx}$, where $\alpha$ is the thermal
diffusivity of the material.

Separation of variables with $u(x,t) = X(x)\,T(t)$ splits the problem
into two ordinary differential equations coupled by a separation
constant $-\lambda$: the spatial part becomes an eigenvalue problem, the
temporal part a simple decay equation.

For a rod of length $L$ with ends held at zero temperature, the general
solution is the Fourier sine series
$u(x,t) = \sum_{n=1}^{\infty} b_n \sin\!\left(\frac{n\pi x}{L}\right) e^{-\alpha (n\pi/L)^2 t},$
with coefficients $b_n$ determined by the initial temperature profile.

Physically, the exponential factor says that high spatial frequencies
decay fastest: fine temperature details are smoothed out almost
immediately, while the slowest mode $n = 1$ dominates the long-time
behaviour.
