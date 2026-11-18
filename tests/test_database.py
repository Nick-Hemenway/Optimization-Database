import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from sqlite3 import IntegrityError

import numpy as np
import optwrap as opt
import pytest

from optdb import Database, Iteration, Run
from optdb.database import migrate_v1_to_v2


@pytest.fixture(params=[False, True], ids=["fresh", "migrated"])
def migrated(request):
    return request.param


@pytest.fixture
def v1_db_path() -> Path:
    return Path(__file__).parent / "assets/v1.sqlite"


@pytest.fixture
def db_path(tmp_path) -> Path:
    return Path(tmp_path) / "test.sqlite"


@pytest.fixture
def db(migrated, db_path, v1_db_path):
    if not migrated:
        db = Database(db_path)
    else:
        shutil.copy(v1_db_path, db_path)
        db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def db_with_run(db: Database) -> Database:
    db.add_run(name="foo")
    return db


def test_adding_run_empty(db: Database):
    id_ = db.add_run(name="foo")
    run = db.get_run(id_)
    assert isinstance(run, Run)
    assert run.registry is None
    assert run.parameters is None
    assert run.operating_points is None


def test_adding_run(db: Database):
    reg = opt.Registry()
    reg.add("foo", lower=0, upper=100, default=10)
    reg.add("bar", lower=0, upper=1000, default=100)
    p1 = opt.Parameter("a", units="m")
    p2 = opt.Parameter("b", units="m", default=20)
    op1 = opt.OperatingPointParameter("c")
    op2 = opt.OperatingPointParameter("d")
    reg.add_parameter(p1)
    reg.add_parameter(p2)
    reg.add_operating_point_parameter(op1)
    reg.add_operating_point_parameter(op2)
    params = opt.Parameters(a=1, b=2)
    op = opt.OperatingPoints(c=2, d=[1, 2, 3])
    metadata = "{'key': 123}"
    description = "a description"
    id_ = db.add_run(
        name="foo",
        registry=reg,
        parameters=params,
        operating_points=op,
        metadata=metadata,
        description=description,
    )
    run = db.get_run(id_)
    assert run.registry.to_config() == reg.to_config()
    assert run.parameters == params
    assert run.operating_points == op
    assert run.metadata == metadata
    assert run.description == description
    assert isinstance(run.created_at, datetime)


def test_unique_run_name(db: Database):
    db.add_run("foo")
    with pytest.raises(IntegrityError):
        db.add_run("foo")


def test_adding_multiple_runs(db: Database):
    id1 = db.add_run("foo")
    id2 = db.add_run("bar")
    id3 = db.add_run("baz")
    assert db.get_run(id1).name == "foo"
    assert db.get_run(id2).name == "bar"
    assert db.get_run(id3).name == "baz"
    assert len(db.get_runs()) == 3


def test_variables_round_trip(db_with_run: Database):
    vars = [
        opt.Variable(name="bar", start=0, size=1, lower=0, upper=100, default=10),
        opt.Variable(name="baz", start=1, size=1, lower=0, upper=1000, default=100),
    ]
    for v in vars:
        db_with_run.add_variable(run_id=1, value=v)
    restored = db_with_run.get_variables(run_id=1)
    assert restored == vars


def test_parameters_round_trip(db_with_run: Database):
    params = [
        opt.Parameter(name="foo_param"),
        opt.Parameter(name="bar_param"),
    ]
    for param in params:
        db_with_run.add_parameter(run_id=1, value=param)
    params_out = db_with_run.get_parameters(run_id=1)
    assert params_out == params


def test_op_parameters_round_trip(db_with_run: Database):
    params = [
        opt.OperatingPointParameter(name="foo_param"),
        opt.OperatingPointParameter(name="bar_param"),
    ]
    for param in params:
        db_with_run.add_operating_point_parameter(run_id=1, value=param)
    params_out = db_with_run.get_operating_point_parameters(run_id=1)
    assert params_out == params


def test_objectives_round_trip(db_with_run: Database):
    objectives = [
        opt.Objective(target="bar", sense="minimize"),
        opt.Objective(target="baz", sense="maximize"),
    ]
    for obj in objectives:
        db_with_run.add_objective(run_id=1, value=obj)
    restored = db_with_run.get_objectives(run_id=1)
    assert restored == objectives


def test_constraints_round_trip(db_with_run: Database):
    constraints = [
        opt.Constraint(target="bar", lower=0, upper=100),
        opt.Constraint(target="baz", lower=0, upper=1000),
    ]
    for constr in constraints:
        db_with_run.add_constraint(run_id=1, value=constr)
    restored = db_with_run.get_constraints(run_id=1)
    assert restored == constraints


def test_last_generation_number(db_with_run: Database):
    db_with_run.add_iteration(run_id=1, iteration=1)
    db_with_run.add_iteration(run_id=1, iteration=20)
    last = db_with_run.get_last_iteration_number(run_id=1)
    assert last == 20


def test_duplicate_iteration(db_with_run: Database):
    db_with_run.add_iteration(run_id=1, iteration=1)
    with pytest.raises(IntegrityError):
        db_with_run.add_iteration(run_id=1, iteration=1)


def test_iteration_round_trip_empty(db_with_run: Database):
    db_with_run.add_iteration(run_id=1, iteration=1)
    db_with_run.add_iteration(run_id=1, iteration=2)
    gen = db_with_run.get_iteration(run_id=1, iteration=2)
    assert isinstance(gen, Iteration)
    expected = Iteration(
        run_id=1,
        iteration=2,
        designs=None,
        objectives=None,
        constraints=None,
        metrics=None,
        current_population=None,
    )
    assert gen == expected


def test_iteration_round_trip(db_with_run: Database):
    reg = opt.Registry()
    reg.add("var1", lower=0, upper=1000, default=10)
    reg.add("var2", lower=0, upper=2000, default=20)
    reg.add("var3", lower=0, upper=3000, default=30)
    x_scaled = reg.pack_and_scale(var1=[100, 200, 300])
    designs = reg.unpack_scaled(x_scaled)
    metrics_lst = [
        opt.MetricResult(name="foo", value=10),
        opt.MetricResult(name="bar", value=10),
        opt.MetricResult(name="baz", value=10),
    ]
    metrics = {mr.name: mr for mr in metrics_lst}
    obj_lst = [
        opt.ObjectiveResult(
            name="foo1", metric_result=metrics["foo"], scale=1, sense="minimize"
        ),
        opt.ObjectiveResult(
            name="bar1", metric_result=metrics["bar"], scale=10, sense="maximize"
        ),
    ]
    objectives = {o.name: o for o in obj_lst}
    constrs_lst = [
        opt.ConstraintResult(
            name="bar2", metric_result=metrics["bar"], lower=0, upper=100, scale=10
        ),
        opt.ConstraintResult(
            name="baz1", metric_result=metrics["baz"], lower=0, upper=1000, scale=1
        ),
    ]
    constraints = {constr.name: constr for constr in constrs_lst}

    X = np.arange(25).reshape(5, 5) * np.pi  # current population
    db_with_run.add_iteration(run_id=1, iteration=1)
    db_with_run.add_iteration(
        run_id=1,
        iteration=2,
        designs=designs,
        objectives=objectives,
        constraints=constraints,
        metrics=metrics,
        current_population=X,
    )
    gen = db_with_run.get_iteration(run_id=1, iteration=2)
    assert gen.iteration == 2
    assert gen.objectives == objectives
    assert gen.constraints == constraints
    assert gen.metrics == metrics
    assert np.allclose(gen.current_population, X)
    assert set(designs.keys()) == set(gen.designs.keys())
    for key, arr in designs.items():
        assert np.allclose(gen.designs[key], arr)


def test_migration_v1_to_v2(db_path, v1_db_path):
    shutil.copy(v1_db_path, db_path)
    conn = sqlite3.connect(db_path)
    migrate_v1_to_v2(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2


def test_migration_v1_to_latest(db_path, v1_db_path):
    shutil.copy(v1_db_path, db_path)
    db = Database(db_path)
    assert db.get_user_version() == db.CURRENT_VERSION
