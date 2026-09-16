import numpy as np
import pandas as pd
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

import pycam.optimize.database.schema as sc
from pycam.optimize import (
    Constraint,
    Constraints,
    FixedParam,
    Objective,
    Objectives,
    SimulationMetric,
    SimulationMetrics,
    SimulationParameters,
    SweepParam,
    VariableParam,
)
from pycam.util import CaseList


# import time
class DataBase:
    def __init__(self, run: sc.Run) -> None:
        # Note: run must already be added to session (e.g. session.add(run))
        self.run = run

    def get_metric(self, name: str, session: Session) -> sc.Metric:
        session.add(self.run)
        for metric in self.run.metrics:
            if metric.name == name:
                return metric

    def get_variable_param(self, name: str, session: Session) -> sc.VariableParam:
        session.add(self.run)
        for param in self.run.variable_params:
            if param.name == name:
                return param

    def add_metric(self, metric: SimulationMetric, session: Session) -> sc.Metric:
        session.add(self.run)
        attrs = {
            attr: getattr(metric, attr) for attr in "name unit label notes".split()
        }
        attrs["run"] = self.run
        obj = sc.Metric(**attrs)
        session.add(obj)

    def add_objective(self, objective: Objective, session: Session):
        metric = self.get_metric(name=objective.name, session=session)
        obj = sc.Objective(
            sign=objective.sign,
            notes=objective.notes,
            metric=metric,
            fail_return_value=objective.fail_return_value,
        )
        session.add(obj)

    def add_constraint(self, constraint: Constraint, session: Session):
        metric = self.get_metric(name=constraint.name, session=session)
        lower, upper = constraint.get_bounds()
        if lower == -np.inf:
            lower = None
        if upper == np.inf:
            upper = None
        obj = sc.Constraint(
            lower_bound=lower,
            upper_bound=upper,
            notes=constraint.notes,
            metric=metric,
            fail_return_value=constraint.fail_return_value,
        )
        session.add(obj)

    def add_metrics(self, metrics: SimulationMetrics, session: Session):
        for metric in metrics:
            self.add_metric(metric, session)

    def add_objectives(self, objectives: Objectives, session: Session):
        for objective in objectives:
            self.add_objective(objective=objective, session=session)

    def add_constraints(self, constraints: Constraints, session: Session):
        for constraint in constraints:
            self.add_constraint(constraint=constraint, session=session)

    def add_variable_param(self, param: VariableParam, session: Session):
        session.add(self.run)
        lower, upper = param.bounds
        obj = sc.VariableParam(
            name=param.name,
            lower_bound=lower,
            upper_bound=upper,
            label=param.label,
            unit=param.unit,
            notes=param.notes,
            run=self.run,
        )
        session.add(obj)

    def add_fixed_param(self, param: FixedParam, session: Session):
        session.add(self.run)
        name = param.name
        obj = sc.FixedParam(
            name=name,
            run=self.run,
            value=param.value,
            label=param.label,
            unit=param.unit,
            notes=param.notes,
        )
        session.add(obj)

    def add_sweep_param(self, param: SweepParam, session: Session):
        session.add(self.run)
        name = param.name
        obj = sc.SweepParam(
            name=name,
            run=self.run,
            label=param.label,
            unit=param.unit,
            notes=param.notes,
        )
        obj.values = [sc.SweepParamValue(value=val) for val in param.value]
        session.add(obj)

    def add_simulation_parameters(
        self, sim_params: SimulationParameters, session: Session
    ):
        for param in sim_params.variable_params.values():
            self.add_variable_param(param, session=session)

        for param in sim_params.fixed_params.values():
            self.add_fixed_param(param, session=session)

        for param in sim_params.sweep_params.values():
            self.add_sweep_param(param, session=session)

    def add_quantities(
        self,
        metrics: SimulationMetrics,
        objectives: Objectives,
        constraints: Constraints,
        sim_params: SimulationParameters,
        session: Session,
    ):
        self.add_metrics(metrics, session=session)
        self.add_objectives(objectives, session=session)
        self.add_constraints(constraints, session=session)
        self.add_simulation_parameters(sim_params, session=session)

    def add_generation(self, generation, session):
        session.add(self.run)
        # Make sure we only have unique generation numbers for each run
        gen_numbers = [gen.number for gen in self.run.generations]
        if generation in gen_numbers:
            raise ValueError(
                "The generation number already exists in the database for this run"
            )

        self.current_generation = sc.Generation(number=generation, run=self.run)
        session.add(self.current_generation)

    def add_designs(self, cases: CaseList, session: Session):
        # first create design objects and add to session
        self.designs = [
            sc.Design(generation=self.current_generation, number=i)
            for i, _ in enumerate(cases)
        ]
        session.add_all(self.designs)

        # then create parameters values to associate with each design
        for case, design in zip(cases, self.designs):
            for name, val in case.items():
                session.add(
                    sc.VariableParamValue(
                        value=val,
                        design=design,
                        param=self.get_variable_param(name=name, session=session),
                    )
                )

    def add_evaluated_metrics(
        self, evaluated_metrics: dict[str, list], session: Session
    ):
        # add all evaluated metrics
        for metric_name, vals in evaluated_metrics.items():
            for design, val in zip(self.designs, vals):
                session.add(
                    sc.MetricValue(
                        value=val,
                        design=design,
                        metric=self.get_metric(name=metric_name, session=session),
                    )
                )

    def add_post_selection_members(
        self, members: list[dict[str, float]], session: Session
    ):
        for member in members:
            # start = time.perf_counter()
            design = self.get_design(param_set=member, session=session)
            # stop = time.perf_counter()
            # print(stop - start)
            membership = sc.PostSelectionMember(
                design=design, generation=self.current_generation
            )
            session.add(membership)

    def get_design(self, param_set: dict, session: Session):
        session.add(self.run)
        conditions = [
            and_(sc.VariableParam.name == name, sc.VariableParamValue.value == val)
            for name, val in param_set.items()
        ]
        conditions = or_(*conditions)

        query = (
            select(sc.Design)
            .select_from(select(sc.Run).where(sc.Run.id == self.run.id).subquery())
            .join(sc.Generation)
            .join(sc.Design)
            .join(sc.VariableParamValue)
            .join(sc.VariableParam)
            .where(conditions)
            .group_by(sc.Design.id)
            .having(func.count(sc.Design.id) == len(param_set))
            # if duplicates (which there shouldn't be) return most recent design
            .order_by(sc.Generation.number.desc())
        )
        return session.scalar(query)

    @staticmethod
    def get_design_params(design_id: int, session: Session):
        objs = session.execute(
            select(sc.VariableParamValue, sc.VariableParam)
            .join(sc.Design)
            .join(sc.VariableParam)
            .where(sc.Design.id == design_id)
        ).all()

        return {param.name: val.value for val, param in objs}


def write_to_database(
    generation_number: int,
    designs_pre_selection: CaseList,
    evaluated_metrics: dict[str, np.ndarray],
    designs_post_selection: CaseList,
    dbase: DataBase,
    session: Session,
) -> None:
    # Order matters here since designs reference a generation, metrics reference a design, etc.
    dbase.add_generation(generation=generation_number, session=session)
    dbase.add_designs(cases=designs_pre_selection, session=session)
    dbase.add_evaluated_metrics(evaluated_metrics=evaluated_metrics, session=session)
    dbase.add_post_selection_members(members=designs_post_selection, session=session)


def get_init_population(
    run_id: int,
    generation_number: int,
    sim_params: SimulationParameters,
    session: Session,
) -> np.ndarray:
    """Get previous population for initializing new optimization

    Parameters
    ----------
    run_id : int
        Unique id of run to search within (primary key)
    generation_number : int
        Generation number (different from generation id) to extract population from.
        If negative, count from the end of the run (e.g. -1 corresponds to last generation,
        -2 corresponds to second to last generation, etc.)
    sim_params : SimulationParameters
        SimulationParameters object. This is required to make sure the parameters are
        ordered consistently with what the current optimization is set up to use
    session : Session
        SQLAlchemy session object connected to database

    Returns
    -------
    np.ndarray
        2-Dimensional array where each row corresponds to a design
    """
    if generation_number < 0:
        # only need to compute last gen if generation_number is negative
        last_gen = get_last_generation_number(run_id, session)
        generation_number = last_gen + (generation_number + 1)

    # get all design ids from selected generation
    design_ids = get_design_ids_for_generation(
        run_id,
        generation_number=generation_number,
        session=session,
    )
    # get all designs for entire run
    all_designs = get_designs(run_id, session, fixed_params=False)
    # downsample from all designs to only selected design ids,
    # then convert to list of dicts of params
    cases = all_designs.loc[design_ids].to_dict(orient="records")
    # return cases properly ordered based on sim param specification
    return sim_params.cases_to_x(cases)


def get_run(run_id: int, session: Session) -> sc.Run:
    return session.scalar(select(sc.Run).where(sc.Run.id == run_id))


def get_last_run_id(session: Session) -> int:
    return session.scalar(select(func.max(sc.Run.id)))


def get_last_generation_number(run_id: int, session: Session) -> int:
    last_gen = session.scalar(
        select(func.max(sc.Generation.number)).where(sc.Generation.run_id == run_id)
    )
    if last_gen is None:
        raise ValueError("There are no generations for the given run!")
    return last_gen


def get_generation_id(generation_number: int, run_id: int, session: Session):
    # Note: we don't have to make sure there's only a single unique generation
    # id for the given generation number and run id because we have data integrity
    # checks at the point of input. i.e. in the DataBase.add_generation method,
    # we verify that the generation doesn't already exist for the given run
    return session.scalar(
        select(sc.Generation.id)
        .where(sc.Generation.run_id == run_id)
        .where(sc.Generation.number == generation_number)
    )


def _unique_ordered_list(lst: list):
    # We don't want duplicate values in param names, we could use set but sets are not ordered
    # thus we will create our own ordered set
    return list({param: None for param in lst}.keys())


def get_variable_param_names(run_id: int, session: Session) -> list[str]:
    """Return ordered list of unique variable param names for a given run id

    Parameters
    ----------
    run_id : int
        Unique id of run (primary key)
    session : Session
        SQLAlchemy Session object

    Returns
    -------
    variable_param_names : list[str]
        List of the variable parameter names orded by the sequence in which the parameters
        were added to the database
    """
    variable_params = session.scalars(
        select(sc.VariableParam)
        .where(sc.VariableParam.run_id == run_id)
        .order_by(sc.VariableParam.id)
    ).all()
    return _unique_ordered_list([param.name for param in variable_params])


def get_fixed_param_names(run_id: int, session: Session) -> list[str]:
    """Return ordered list of unique fixed param names for a given run id

    Parameters
    ----------
    run_id : int
        Unique id of run (primary key)
    session : Session
        SQLAlchemy Session object

    Returns
    -------
    list[str]
        List of the fixed parameter names ordered by the sequence in which the paramaters
        were added to the database
    """
    fixed_params = session.scalars(
        select(sc.FixedParam)
        .where(sc.FixedParam.run_id == run_id)
        .order_by(sc.FixedParam.id)
    ).all()
    return _unique_ordered_list([param.name for param in fixed_params])


def get_fixed_params(run_id: int, session: Session):
    query = """
    SELECT * FROM fixed_param
    WHERE run_id = :run_id;
    """
    return pd.read_sql_query(
        query, con=session.connection(), params={"run_id": run_id}, index_col="id"
    )


def get_designs(
    run_id: int, session: Session, fixed_params: bool = False
) -> pd.DataFrame:
    query = """
    SELECT d.id as design_id, vp.name as param_name, vpv.value as param_value
    FROM design d 
    JOIN variable_param_value vpv ON vpv.design_id = d.id
    JOIN variable_param vp ON vpv.param_id = vp.id
    JOIN generation g ON d.generation_id = g.id
    WHERE g.run_id = :run_id;
    """
    df = pd.read_sql_query(query, con=session.connection(), params={"run_id": run_id})
    df = df.pivot(index="design_id", columns="param_name", values="param_value")
    param_order = get_variable_param_names(run_id=run_id, session=session)
    if fixed_params:
        param_order += get_fixed_param_names(run_id=run_id, session=session)
        fp = get_fixed_params(run_id=run_id, session=session)
        for i, row in fp.iterrows():
            df[row["name"]] = row["value"]
    return df[param_order]


def get_design_ids_for_generation(
    run_id: int,
    generation_number: int,
    session: Session,
) -> pd.DataFrame:
    generation_id = get_generation_id(
        generation_number=generation_number, run_id=run_id, session=session
    )
    query = """
        SELECT 
        psm.design_id
        FROM post_selection_member psm
        WHERE psm.generation_id = :generation_id;
        """
    return (
        pd.read_sql_query(
            query, session.connection(), params={"generation_id": generation_id}
        )
        .to_numpy()
        .squeeze()
    )


def get_post_selection_members(run_id: int, session: Session) -> pd.DataFrame:
    query = """
    SELECT
    psm.design_id,
    g.number as generation_number
    FROM post_selection_member psm
    JOIN generation g ON psm.generation_id = g.id
    ORDER BY g.number, psm.design_id;
    """
    return pd.read_sql_query(query, con=session.connection(), params={"run_id": run_id})


def get_design_generation_mapping(run_id: int, session: Session) -> pd.DataFrame:
    query = """
    SELECT
    g.number as generation_number,
    d.id as design_id
    FROM generation g
    JOIN design d ON d.generation_id = g.id
    WHERE g.run_id = :run_id
    ORDER BY g.number, d.id;
    """
    return pd.read_sql_query(query, con=session.connection(), params={"run_id": run_id})


def get_runs_table(session):
    return pd.read_sql_table("run", session.connection(), index_col="id")


def get_constraints(run_id: int, session: Session):
    query = """
    SELECT
    mv.design_id,
    m.name as metric_name,
    mv.value as metric_value,
    c.lower_bound,
    c.upper_bound
    FROM metric m
    JOIN metric_value mv on mv.metric_id = m.id
    JOIN "constraint" c on c.metric_id = m.id
    WHERE m.run_id = :run_id
    ORDER BY design_id;
    """
    df = pd.read_sql_query(query, con=session.connection(), params={"run_id": run_id})
    df["lower_bound"] = df["lower_bound"].fillna(-np.inf)
    df["upper_bound"] = df["upper_bound"].fillna(np.inf)
    excess_lb = df["lower_bound"] - df["metric_value"]
    excess_ub = df["metric_value"] - df["upper_bound"]
    df["CV"] = np.maximum(excess_lb, excess_ub)
    return df


def get_objectives(run_id: int, session: Session):
    query = """
    SELECT
    mv.design_id,
    m.name as metric_name,
    mv.value as metric_value,
    o.sign,
    o.sign*mv.value as objective_value
    FROM metric m
    JOIN metric_value mv on mv.metric_id = m.id
    JOIN objective o on o.metric_id = m.id
    WHERE m.run_id = :run_id
    ORDER BY design_id;
    """
    return pd.read_sql_query(query, con=session.connection(), params={"run_id": run_id})


def get_metrics(
    run_id: int,
    session: Session,
    pivot: bool = True,
):
    query = """
    SELECT
    mv.design_id,
    m.name as metric_name,
    mv.value as metric_value
    FROM metric m
    JOIN metric_value mv ON mv.metric_id = m.id
    WHERE m.run_id = :run_id
    ORDER BY mv.design_id;
    """
    df = pd.read_sql_query(query, con=session.connection(), params={"run_id": run_id})
    if pivot:
        df = df.pivot(
            index="design_id",
            columns="metric_name",
            values="metric_value",
        )
    return df
