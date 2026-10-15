from sqlite3 import IntegrityError

import optwrap as opt
import pytest

from optdb import Database, Run


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "foo.db")
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
    id_ = db.add_run(
        name="foo",
        registry=reg,
        parameters=params,
        operating_points=op,
    )
    run = db.get_run(id_)
    assert run.registry.to_config() == reg.to_config()
    assert run.parameters == params
    assert run.operating_points == op


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


# def test_adding_objective(db_with_run: Database):
#     obj = opt.Objective(metric="bar", sense="maximize")
#     db_with_run.add_objective(run_id=1, value=obj)


# def test_adding_constraint(db_with_run: Database):
#     constr = opt.Constraint(metric="bar", lower=0, upper=100)
#     db_with_run.add_constraint(run_id=1, value=constr)


# def test_variable_round_trip(db_with_run: Database):
#     vars = [
#         opt.registry.Variable(name="foo_var", start=0, size=1, lower=0, upper=100),
#         opt.registry.Variable(name="bar_var", start=1, size=1, lower=0, upper=100),
#     ]
#     for var in vars:
#         db_with_run.add_variable(run_id=1, value=var)
#     vars_out = db_with_run.get_variables(run_id=1)
#     assert vars_out == vars
