import pytest
import numpy as np
import toppra
import toppra.constraint as constraint

toppra.setup_logging(level="DEBUG")

try:
    import mosek
    FOUND_MOSEK = True
except ImportError:
    FOUND_MOSEK = False

try:
    import cvxpy
    FOUND_CXPY = True
except ImportError:
    FOUND_CXPY = False


@pytest.fixture(params=[(0, 0)])
def vel_accel_robustaccel(request):
    "Velocity + Acceleration + Robust Acceleration constraint"
    dtype_a, dtype_ra = request.param
    vlims = np.array([[-1, 1], [-1, 2], [-1, 4]], dtype=float)
    alims = np.array([[-1, 1], [-1, 2], [-1, 4]], dtype=float)
    vel_cnst = constraint.JointVelocityConstraint(vlims)
    accl_cnst = constraint.JointAccelerationConstraint(alims, dtype_a)
    robust_accl_cnst = constraint.RobustCanonicalLinearConstraint(accl_cnst, [0.5, 0.1, 2.0], dtype_ra)
    yield vel_cnst, accl_cnst, robust_accl_cnst


@pytest.fixture
def path():
    np.random.seed(1)
    path = toppra.SplineInterpolator(np.linspace(0, 1, 5), np.random.randn(5, 3))
    yield path

@pytest.mark.parametrize("i", [0, 5, 10])
@pytest.mark.parametrize("H", [np.array([[1.5, 0], [0, 1.0]]), np.zeros((2, 2)), None])
@pytest.mark.parametrize("g", [np.array([0.2, -1]), np.array([0.5, 1]), np.array([2.0, 1])])
@pytest.mark.parametrize("x_ineq", [(-1, 1), (0.2, 0.2), (0.4, 0.3), (None, None)])
@pytest.mark.parametrize("solver_name", ['cvxpy', 'ECOS'])
def test_vel_robust_accel(vel_accel_robustaccel, path, solver_name, i, H, g, x_ineq):
    "Case 1: only velocity and robust acceleration constraints"
    vel_c, _, robust_acc_c = vel_accel_robustaccel
    path_dist = np.linspace(0, path.get_duration(), 10)
    if solver_name == "cvxpy":
        solver = toppra.solverwrapper.cvxpyWrapper([vel_c, robust_acc_c], path, path_dist)
    elif solver_name == "ECOS":
        return
    else:
        assert False

    xmin, xmax = x_ineq
    xnext_min = 0
    xnext_max = 1

    # Results from solverwrapper to test
    result = solver.solve_stagewise_optim(i, H, g, xmin, xmax, xnext_min, xnext_max)

    # Results from cvxpy, used as the actual, desired values
    ux = cvxpy.Variable(2)
    u = ux[0]
    x = ux[1]

    _, _, _, _, _, _, xbound = vel_c.compute_constraint_params(path, path_dist)
    a, b, c, P = robust_acc_c.compute_constraint_params(path, path_dist)
    Di = path_dist[i + 1] - path_dist[i]
    cvx_constraints = [
        xbound[i, 0] <= x, x <= xbound[i, 1],
        x + u * 2 * Di <= xnext_max,
        x + u * 2 * Di >= xnext_min,
    ]
    for j in range(a.shape[1]):
        cvx_constraints.append(
            a[i, j] * u + b[i, j] * x + c[i, j]
            + cvxpy.norm(P[i, j].T[:, :2] * ux + P[i, j].T[:, 2]) <= 0
        )
    if xmin is not None:
        cvx_constraints.append(x <= xmax)
        cvx_constraints.append(x >= xmin)
    if H is not None:
        objective = cvxpy.Minimize(0.5 * cvxpy.quad_form(ux, H) + g * ux)
    else:
        objective = cvxpy.Minimize(g * ux)
    problem = cvxpy.Problem(objective, cvx_constraints)
    if FOUND_MOSEK:
        problem.solve(solver="MOSEK", verbose=True)
    else:
        problem.solve(solver="ECOS", verbose=True)
    if problem.status == "optimal":
        actual = np.array(ux.value).flatten()
        np.testing.assert_allclose(
            result.flatten(), actual.flatten(), atol=5e-3, rtol=1e-5)
    else:
        assert np.all(np.isnan(result))
    assert False


def test_robust_accel_only(vel_accel_robustaccel):
    "Case 2: only robust acceleration constraints"
    assert False

def test_accel_robust_accel(vel_accel_robustaccel):
    "Case 3: Both accel and robust accel"

def test_compare_accel_robust_accel(vel_accel_robustaccel):
    "Case 4: If robust accel has very small perturbation ellipsoid, it should be equivalent to acceleration constraint."
