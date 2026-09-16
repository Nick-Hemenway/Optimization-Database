from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from sqlalchemy import ForeignKey, create_engine, func, text
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "run"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    code_commit: Mapped[str]
    start_time: Mapped[datetime] = mapped_column(default=datetime.now)
    notes: Mapped[Optional[str]]

    generations: Mapped[list["Generation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["Metric"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    variable_params: Mapped[list["VariableParam"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    fixed_params: Mapped[list["FixedParam"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    sweep_params: Mapped[list["SweepParam"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Generation(Base):
    __tablename__ = "generation"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    number: Mapped[int]
    time: Mapped[str] = mapped_column(default=func.now())
    label: Mapped[Optional[str]]
    notes: Mapped[Optional[str]]

    run: Mapped[Run] = relationship(back_populates="generations")
    designs: Mapped[list["Design"]] = relationship(
        back_populates="generation", cascade="all, delete-orphan"
    )
    post_selection_members: Mapped[list["PostSelectionMember"]] = relationship(
        back_populates="generation", cascade="all, delete-orphan"
    )


class Design(Base):
    __tablename__ = "design"

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generation.id"))
    number: Mapped[int]
    label: Mapped[Optional[str]]
    notes: Mapped[Optional[str]]

    generation: Mapped[Generation] = relationship(back_populates="designs")
    param_values: Mapped[list["VariableParamValue"]] = relationship(
        back_populates="design", cascade="all, delete-orphan"
    )
    metric_values: Mapped[list["MetricValue"]] = relationship(
        back_populates="design", cascade="all, delete-orphan"
    )
    post_selection_members: Mapped[list["PostSelectionMember"]] = relationship(
        back_populates="design", cascade="all, delete-orphan"
    )


class Metric(Base):
    __tablename__ = "metric"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    name: Mapped[str]
    label: Mapped[Optional[str]]
    unit: Mapped[Optional[str]]
    notes: Mapped[Optional[str]]

    run: Mapped[Run] = relationship(back_populates="metrics")
    values: Mapped[list["MetricValue"]] = relationship(back_populates="metric")
    objectives: Mapped[list["Objective"]] = relationship(
        back_populates="metric", cascade="all, delete-orphan"
    )
    constraints: Mapped[list["Constraint"]] = relationship(
        back_populates="metric", cascade="all, delete-orphan"
    )


class MetricValue(Base):
    __tablename__ = "metric_value"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric.id"))
    design_id: Mapped[int] = mapped_column(ForeignKey("design.id"))
    value: Mapped[Optional[float]]

    metric: Mapped[Metric] = relationship(back_populates="values")
    design: Mapped[Design] = relationship(back_populates="metric_values")


class Objective(Base):
    __tablename__ = "objective"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric.id"))
    fail_return_value: Mapped[Optional[float]]
    sign: Mapped[int]
    notes: Mapped[Optional[str]]

    metric: Mapped[Metric] = relationship()


class Constraint(Base):
    __tablename__ = "constraint"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric.id"))
    fail_return_value: Mapped[Optional[float]]
    lower_bound: Mapped[Optional[float]]
    upper_bound: Mapped[Optional[float]]
    notes: Mapped[Optional[str]]

    metric: Mapped[Metric] = relationship(back_populates="constraints")


class VariableParam(Base):
    __tablename__ = "variable_param"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    name: Mapped[str]
    lower_bound: Mapped[float]
    upper_bound: Mapped[float]
    label: Mapped[Optional[str]]
    unit: Mapped[Optional[str]]
    notes: Mapped[Optional[str]]

    run: Mapped[Run] = relationship(back_populates="variable_params")
    values: Mapped[list["VariableParamValue"]] = relationship(
        back_populates="param", cascade="all, delete-orphan"
    )


class VariableParamValue(Base):
    __tablename__ = "variable_param_value"

    id: Mapped[int] = mapped_column(primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("design.id"))
    param_id: Mapped[int] = mapped_column(ForeignKey("variable_param.id"))
    value: Mapped[float]

    design: Mapped[Design] = relationship(back_populates="param_values")
    param: Mapped[VariableParam] = relationship(back_populates="values")


class FixedParam(Base):
    __tablename__ = "fixed_param"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    name: Mapped[str]
    value: Mapped[float]
    label: Mapped[Optional[str]]
    unit: Mapped[Optional[str]]
    notes: Mapped[Optional[str]]

    run: Mapped[Run] = relationship(back_populates="fixed_params")


class SweepParam(Base):
    __tablename__ = "sweep_param"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("run.id"))
    name: Mapped[str]
    label: Mapped[Optional[str]]
    unit: Mapped[Optional[str]]
    notes: Mapped[Optional[str]]

    run: Mapped[Run] = relationship(back_populates="sweep_params")
    values: Mapped[list["SweepParamValue"]] = relationship(
        back_populates="param", cascade="all, delete-orphan"
    )


class SweepParamValue(Base):
    __tablename__ = "sweep_param_value"

    id: Mapped[int] = mapped_column(primary_key=True)
    param_id: Mapped[int] = mapped_column(ForeignKey("sweep_param.id"))
    value: Mapped[float]

    param: Mapped[SweepParam] = relationship(back_populates="values")


class PostSelectionMember(Base):
    __tablename__ = "post_selection_member"

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generation.id"))
    design_id: Mapped[int] = mapped_column(ForeignKey("design.id"))

    generation: Mapped[Generation] = relationship(
        back_populates="post_selection_members"
    )
    design: Mapped[Design] = relationship(back_populates="post_selection_members")


def get_maker(path: Optional[Union[Path, str]] = None, echo: bool = False):
    if path:
        path = Path(path).resolve()
        # Make parent folders for path if non-existent
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path}", echo=echo)
    else:
        engine = create_engine("sqlite:///", echo=echo)

    maker = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    loc = Path(__file__).parent
    with maker.begin() as session:
        with open(loc / "views.sql") as f:
            txt = f.read()
        blocks = txt.split(";")
        for block in blocks:
            session.execute(text(block.strip()))
            # txt = f.read().split(';')
        # for block in txt:
        # session.execute(block.strip())
    return maker


if __name__ == "__main__":
    maker = get_maker("test.sqlite")

    run = Run(name="Run 1", notes="test note", code_commit="asdflkjasdf")
    gen = Generation(number=1, run=run)
    metric = Metric(name="power", label="Power [hp]", run=run)
    v_param = VariableParam(
        name="int_duration", lower_bound=10, upper_bound=100, run=run
    )
    f_param = FixedParam(name="ramp", value=10, run=run)
    s_param = SweepParam(name="rpm", run=run)

    design = Design(generation=gen)

    s_param_v1 = SweepParamValue(value=1000, param=s_param)
    s_param_v2 = SweepParamValue(value=2000, param=s_param)
    s_param_v3 = SweepParamValue(value=3000, param=s_param)

    v_param_1 = VariableParamValue(value=20, param=v_param, design=design)

    o1 = Objective(name="max_hp", metric=metric, sign=-1)
    c1 = Constraint(name="hp", lower_bound=100, upper_bound=None, metric=metric)

    member = PostSelectionMember(generation=gen, design=design)

    with maker.begin() as session:
        session.add(run)
        session.add(gen)
        session.add(metric)
        session.add(v_param)
        session.add(f_param)
        session.add(s_param)
        session.add(design)
        session.add(s_param_v1)
        session.add(s_param_v2)
        session.add(s_param_v3)
        session.add(v_param_1)
        session.add(o1)
        session.add(c1)
        session.add(member)
