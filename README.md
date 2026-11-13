# ASCII
Animated ASCII Art coded in Python
There will be multiple files that can be used individually using the command "python filename.py"

dragons.py:

A real-time 3D ASCII-art engine in pure Python, and a flock of dragons
swirling around each other inside it.

What's going on 
  * Software 3D: perspective projection, z-buffer, per-pixel sphere
    shading with a point light (the "storm heart" at the centre), a moon-like
    directional light, rim light, depth fog and belly/back colouring.
  * Each dragon is a 3D chain of ~40 shaded spheres that follows its head
    along a parametric path at equal arclength spacing (like a rope), plus
    spines, horns, glowing eyes, a hinged jaw, and two flapping wings.
  * Five formations - tornado, trefoil knot, Hopf link (two interlocked
    rings), sphere orbit and twin helix - blended into each other with a
    smoothstep so the whole flock morphs midflight.
  * Fire/ice/poison breath particles, swirling dust funnel, lightning,
    parallax starfield + nebula, a free-orbit camera and chase cameras that
    ride behind any dragon.

Controls
    n / p      next / previous formation (morphs smoothly)
    h          hold the current formation (toggle auto-cycling)
    c          cycle camera: orbit -> chase dragon 1 -> chase dragon 2 ...
    f          everybody breathes fire
    + / -      add / remove a dragon (2..6)
    q          quit              (Ctrl+C also works)

Run:   python3 dragons.py [number_of_dragons 2-6]

Pure standard library. Needs a 256-colour terminal; bigger window = better
(try 130x40).
