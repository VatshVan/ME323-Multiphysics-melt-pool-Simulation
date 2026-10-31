# Governing Equations

## 1. Continuity Equation

For incompressible flow:

```math
\nabla \cdot \mathbf{u} = 0
```

## 2. Momentum Equation

Laminar momentum conservation with buoyancy and mushy-zone damping:

```math
\rho \left(
\frac{\partial \mathbf{u}}{\partial t}
+ \mathbf{u}\cdot\nabla\mathbf{u}
\right)
=
-\nabla p
+\mu\nabla^2\mathbf{u}
-\rho\beta(T-T_{\mathrm{ref}})\mathbf{g}
-\mu\frac{180}{\lambda^2}
\frac{f_s^2}{(1-f_s)^3}\mathbf{u}
```

### Mushy-Zone Damping Parameter

```math
\lambda = \sqrt{\frac{180\mu}{A_{\mathrm{mush}}}}
= 79\,\mu\mathrm{m}
```

```math
A_{\mathrm{mush}} = 10^8
```

The mushy-zone damping term suppresses fluid motion as the material solidifies.

### Variables

| Symbol | Definition | SI Unit |
|---|---|---|
| $\rho$ | Material density | $\mathrm{kg\,m^{-3}}$ |
| $\mathbf{u}$ | Velocity vector | $\mathrm{m\,s^{-1}}$ |
| $t$ | Time | $\mathrm{s}$ |
| $p$ | Pressure | $\mathrm{Pa}$ |
| $\mu$ | Dynamic viscosity | $\mathrm{Pa\,s}$ |
| $\beta$ | Thermal expansion coefficient | $\mathrm{K^{-1}}$ |
| $T$ | Temperature | $\mathrm{K}$ |
| $T_{\mathrm{ref}}$ | Reference temperature | $\mathrm{K}$ |
| $\mathbf{g}$ | Gravitational acceleration vector | $\mathrm{m\,s^{-2}}$ |
| $f_s$ | Solid fraction | Dimensionless |
| $\lambda$ | Mushy-zone length parameter | $\mathrm{m}$ |
| $A_{\mathrm{mush}}$ | Mushy-zone damping coefficient | Model-dependent |

## 3. Energy Equation

Enthalpy-based energy conservation, including convection, heat conduction, latent heat, and laser energy input:

```math
\rho c_p\left(
\frac{\partial T}{\partial t}
+\mathbf{u}\cdot\nabla T
\right)
=
\nabla\cdot(k\nabla T)
+\rho L_f\frac{\partial f_s}{\partial t}
+q_{\mathrm{laser}}
```

### Solid Fraction

The solid fraction is defined using a cosine-smoothed transition between the solidus and liquidus temperatures.

```math
f_s(T)=
\begin{cases}
1, & T \leq 1878\,\mathrm{K}\\
\text{Cosine-smoothed transition}, & 1878<T<1928\,\mathrm{K}\\
0, & T \geq 1928\,\mathrm{K}
\end{cases}
```

### Temperature-Dependent Material Properties

Thermal conductivity and specific heat capacity are interpolated between solid and liquid values using the solid fraction.

```math
k = f_s k_s + (1-f_s)k_l
```

```math
c_p = f_s c_{p,s} + (1-f_s)c_{p,l}
```

### Variables

| Symbol | Definition | SI Unit |
|---|---|---|
| $c_p$ | Specific heat capacity | $\mathrm{J\,kg^{-1}\,K^{-1}}$ |
| $k$ | Thermal conductivity | $\mathrm{W\,m^{-1}\,K^{-1}}$ |
| $k_s$ | Solid thermal conductivity | $\mathrm{W\,m^{-1}\,K^{-1}}$ |
| $k_l$ | Liquid thermal conductivity | $\mathrm{W\,m^{-1}\,K^{-1}}$ |
| $c_{p,s}$ | Solid specific heat capacity | $\mathrm{J\,kg^{-1}\,K^{-1}}$ |
| $c_{p,l}$ | Liquid specific heat capacity | $\mathrm{J\,kg^{-1}\,K^{-1}}$ |
| $L_f$ | Latent heat of fusion | $\mathrm{J\,kg^{-1}}$ |
| $q_{\mathrm{laser}}$ | Volumetric laser heat source | $\mathrm{W\,m^{-3}}$ |
| $f_s$ | Solid fraction | Dimensionless |
| $T$ | Temperature | $\mathrm{K}$ |

## 4. Boundary Conditions

### 4.1 Top Surface: Marangoni Convection

The tangential stress at the free surface is driven by temperature-dependent surface tension.

```math
\mu\frac{\partial \mathbf{u}_t}{\partial n}
=
f_L\frac{d\sigma}{dT}\nabla_s T
```

The normal velocity at the surface is zero:

```math
\mathbf{u}\cdot\mathbf{n}=0
```

The surface-tension temperature coefficient is:

```math
\frac{d\sigma}{dT}
=
-2.6\times10^{-4}\,\mathrm{N\,m^{-1}\,K^{-1}}
```

For simulations without Marangoni effects:

```math
\left.\frac{d\sigma}{dT}\right|_{\mathrm{noMa}}=0
```

#### Variables

| Symbol | Definition | SI Unit |
|---|---|---|
| $\mathbf{u}_t$ | Tangential velocity vector | $\mathrm{m\,s^{-1}}$ |
| $n$ | Surface-normal coordinate | $\mathrm{m}$ |
| $\mathbf{n}$ | Outward unit normal vector | Dimensionless |
| $f_L$ | Liquid fraction | Dimensionless |
| $\sigma$ | Surface tension | $\mathrm{N\,m^{-1}}$ |
| $d\sigma/dT$ | Surface-tension temperature coefficient | $\mathrm{N\,m^{-1}\,K^{-1}}$ |
| $\nabla_s T$ | Surface temperature gradient | $\mathrm{K\,m^{-1}}$ |

### 4.2 Heat Loss at Outer Surfaces

Convective and radiative heat losses are applied to the outer surfaces, except the bottom surface.

```math
-k\frac{\partial T}{\partial n}
=
h(T-T_\infty)
+\varepsilon\sigma_{\mathrm{SB}}(T^4-T_\infty^4)
```

Boundary-condition parameters:

```math
h=25\,\mathrm{W\,m^{-2}\,K^{-1}}
```

```math
\varepsilon=0.54
```

```math
T_\infty=293\,\mathrm{K}
```

#### Variables

| Symbol | Definition | SI Unit |
|---|---|---|
| $h$ | Convective heat-transfer coefficient | $\mathrm{W\,m^{-2}\,K^{-1}}$ |
| $\varepsilon$ | Surface emissivity | Dimensionless |
| $\sigma_{\mathrm{SB}}$ | Stefan–Boltzmann constant | $\mathrm{W\,m^{-2}\,K^{-4}}$ |
| $T_\infty$ | Ambient temperature | $\mathrm{K}$ |
| $k$ | Thermal conductivity | $\mathrm{W\,m^{-1}\,K^{-1}}$ |
| $n$ | Surface-normal coordinate | $\mathrm{m}$ |

### 4.3 Bottom Surface: Convection Only

Radiative heat loss is omitted at the bottom surface.

```math
-k\frac{\partial T}{\partial n}
=
h(T-T_\infty)
```

### 4.4 Symmetry Plane

At the symmetry plane, $y=0$, there is no heat flux across the plane.

```math
\left.\frac{\partial T}{\partial n}\right|_{y=0}=0
```

There is also no flow across the symmetry plane.

```math
\mathbf{u}\cdot\mathbf{n}=0
```

## 5. Laser Heat Source

The volumetric heat source uses AdditiveFOAM's `superGaussian` formulation with exponent $k=2$, corresponding to a Gaussian distribution.

```math
q(x,y,z,t)
=
\frac{\eta P}{V_0}
\exp\left[
-\frac{2\left((x-x_0-vt)^2+y^2\right)}{r^2}
-\frac{2z^2}{d^2}
\right],
\qquad z\leq0
```

### 5.1 Source Normalization

The normalization volume is defined as:

```math
V_0
=
\frac{\pi}{4}\sqrt{\frac{\pi}{2}}\,r^2d
\approx 0.984\,r^2d
```

The integrated volumetric heat source equals the absorbed laser power.

```math
\iiint_{z\leq0}q(x,y,z,t)\,dV=\eta P
```

### 5.2 Surface Heat-Flux Distribution

Integrating the volumetric source over depth gives the standard Gaussian surface heat-flux distribution.

```math
q''(\rho)
=
\frac{2\eta P}{\pi r^2}
\exp\left(-\frac{2\rho^2}{r^2}\right)
```

The radial distance from the instantaneous beam centre is:

```math
\rho=\sqrt{(x-x_0-vt)^2+y^2}
```

The peak surface intensity occurs at the beam centre.

```math
I_{\mathrm{peak}}=\frac{2\eta P}{\pi r^2}
```

### 5.3 Laser Parameters

| Symbol | Definition | SI Unit |
|---|---|---|
| $q$ | Volumetric laser heat-source density | $\mathrm{W\,m^{-3}}$ |
| $q''$ | Surface heat flux | $\mathrm{W\,m^{-2}}$ |
| $\eta$ | Laser absorptivity | Dimensionless |
| $P$ | Laser power | $\mathrm{W}$ |
| $V_0$ | Source normalization volume | $\mathrm{m^3}$ |
| $x,y,z$ | Spatial coordinates | $\mathrm{m}$ |
| $x_0$ | Initial laser position along the scan direction | $\mathrm{m}$ |
| $v$ | Laser scan speed | $\mathrm{m\,s^{-1}}$ |
| $t$ | Time | $\mathrm{s}$ |
| $r$ | Laser beam radius at the $1/e^2$ intensity level | $\mathrm{m}$ |
| $d$ | Laser absorption depth | $\mathrm{m}$ |
| $\rho$ | Radial distance from the beam centre | $\mathrm{m}$ |

The absorption depth used in the simulations is:

```math
d=50\,\mu\mathrm{m}
```

### 5.4 Peak Laser Intensity

Validation runs:

| Laser Power | Peak Surface Intensity |
|---|---:|
| $1000\,\mathrm{W}$ | $99\,\mathrm{W\,mm^{-2}}$ |
| $1400\,\mathrm{W}$ | $139\,\mathrm{W\,mm^{-2}}$ |

Earlier study:

```math
I_{\mathrm{peak}}=446\text{--}1146\,\mathrm{W\,mm^{-2}}
```