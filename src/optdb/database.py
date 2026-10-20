import json
import sqlite3
from dataclasses import dataclass, fields
from pathlib import Path

import optwrap as opt


@dataclass
class Run:
    run_id: int
    name: str
    registry: opt.Registry | None
    parameters: opt.Parameters | None
    operating_points: opt.OperatingPoints | None


@dataclass
class Iteration:
    run_id: int
    iteration: int
    objectives: dict[str, opt.ObjectiveResult] | None
    constraints: dict[str, opt.ConstraintResult] | None
    metrics: dict[str, opt.MetricResult] | None


class Database:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(path)
        self._initialize()

    def _initialize(self):
        with self.conn:
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON;")
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    registry TEXT,
                    parameters TEXT,
                    operating_points TEXT,
                    description TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );         
                CREATE TABLE IF NOT EXISTS variables (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    name TEXT NOT NULL,
                    start INTEGER,
                    size INTEGER,
                    lower REAL,
                    upper REAL,
                    units TEXT,
                    description TEXT,
                    label TEXT,
                    scaling TEXT,
                    default_value REAL,
                    FOREIGN KEY (run_id) REFERENCES runs(id),
                    UNIQUE(run_id, name)
                );
                CREATE TABLE IF NOT EXISTS parameters (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    name TEXT NOT NULL,
                    units TEXT,
                    description TEXT,
                    label TEXT,
                    default_value REAL,
                    FOREIGN KEY (run_id) REFERENCES runs(id),
                    UNIQUE(run_id, name)
                );
                CREATE TABLE IF NOT EXISTS operating_point_parameters (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    name TEXT NOT NULL,
                    units TEXT,
                    description TEXT,
                    label TEXT,
                    default_value REAL,
                    FOREIGN KEY (run_id) REFERENCES runs(id),
                    UNIQUE(run_id, name)
                );
                CREATE TABLE IF NOT EXISTS objectives (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    target TEXT,
                    sense TEXT,
                    scale REAL,
                    name TEXT,
                    description TEXT,
                    value_on_fail REAL,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS constraints (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    target TEXT,
                    lower REAL,
                    upper REAL,
                    name TEXT,
                    scale REAL,
                    description TEXT,
                    violation_on_fail REAL,
                    min_auto_scale REAL,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS iterations (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    iteration INTEGER,
                    objectives TEXT,
                    constraints TEXT,
                    metrics TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES runs(id),
                    UNIQUE(run_id, iteration)
                );
                """
            )
            self.conn.execute("PRAGMA user_version = 1")

    def _execute_single(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.conn:
            cursor = self.conn.execute(sql, params)
        return cursor

    def add_run(
        self,
        name: str,
        registry: opt.Registry | None = None,
        parameters: opt.Parameters | None = None,
        operating_points: opt.OperatingPoints | None = None,
        description: str | None = None,
    ) -> int:
        if registry is not None:
            registry = json.dumps(registry.to_config())
        if operating_points is not None:
            operating_points = json.dumps(operating_points.to_dict())
        if parameters is not None:
            parameters = json.dumps(parameters.to_dict())
        c = self._execute_single(
            """
            INSERT INTO runs (name, registry, parameters, operating_points, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, registry, parameters, operating_points, description),
        )
        return c.lastrowid

    def get_runs(self) -> list[Run]:
        rows = self._execute_single("SELECT * FROM runs ORDER BY id ASC").fetchall()
        return [self._sanitize_run_output(row) for row in rows]

    def get_run(self, run_id: int) -> Run:
        row = self._execute_single(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return self._sanitize_run_output(row)

    def _sanitize_run_output(self, row: sqlite3.Row) -> Run:
        row = dict(row)
        if (reg := row["registry"]) is not None:
            reg = opt.Registry.from_config(json.loads(reg))
        if (op := row["operating_points"]) is not None:
            op = opt.OperatingPoints.from_dict(json.loads(op))
        if (params := row["parameters"]) is not None:
            params = opt.Parameters.from_dict(json.loads(params))
        return Run(
            run_id=row["id"],
            name=row["name"],
            registry=reg,
            parameters=params,
            operating_points=op,
        )

    def add_variable(self, run_id: int, value: opt.registry.Variable) -> int:
        c = self._execute_single(
            """
            INSERT INTO variables (run_id, name, start, size, lower, upper, units, description, label, scaling, default_value)
            VALUES (:run_id, :name, :start, :size, :lower, :upper, :units, :description, :label, :scaling, :default_value)
            """,
            {
                "run_id": run_id,
                "name": value.name,
                "start": value.start,
                "size": value.size,
                "lower": value.lower,
                "upper": value.upper,
                "units": value.units,
                "description": value.description,
                "label": value.label,
                "scaling": value.scaling,
                "default_value": value.default,
            },
        )
        return c.lastrowid

    def get_variables(self, run_id: int) -> list[opt.Parameter]:
        rows = self._execute_single(
            """
            SELECT * FROM variables WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
        out = []
        for row in rows:
            row = dict(row)
            row["default"] = row.pop("default_value")
            all_fields = (field.name for field in fields(opt.Variable))
            out.append(
                opt.registry.Variable(**{field: row[field] for field in all_fields})
            )
        return out

    def add_parameter(self, run_id: int, value: opt.Parameter) -> int:
        c = self._execute_single(
            """
            INSERT INTO parameters (run_id, name, units, description, label, default_value)
            VALUES (:run_id, :name, :units, :description, :label, :default_value)
            """,
            {
                "run_id": run_id,
                "name": value.name,
                "units": value.units,
                "description": value.description,
                "label": value.label,
                "default_value": value.default,
            },
        )
        return c.lastrowid

    def get_parameters(self, run_id: int) -> list[opt.Parameter]:
        rows = self._execute_single(
            """
            SELECT * FROM parameters WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
        out = []
        for row in rows:
            row = dict(row)
            row["default"] = row.pop("default_value")  # rename
            all_fields = (field.name for field in fields(opt.Parameter))
            out.append(opt.Parameter(**{field: row[field] for field in all_fields}))
        return out

    def add_operating_point_parameter(
        self, run_id: int, value: opt.OperatingPointParameter
    ) -> int:
        c = self._execute_single(
            """
            INSERT INTO operating_point_parameters (run_id, name, units, description, label, default_value)
            VALUES (:run_id, :name, :units, :description, :label, :default_value)
            """,
            {
                "run_id": run_id,
                "name": value.name,
                "units": value.units,
                "description": value.description,
                "label": value.label,
                "default_value": value.default,
            },
        )
        return c.lastrowid

    def get_operating_point_parameters(
        self, run_id: int
    ) -> list[opt.OperatingPointParameter]:
        rows = self._execute_single(
            """
            SELECT * FROM operating_point_parameters WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
        out = []
        for row in rows:
            row = dict(row)
            row["default"] = row.pop("default_value")
            all_fields = (field.name for field in fields(opt.OperatingPointParameter))
            out.append(
                opt.OperatingPointParameter(
                    **{field: row[field] for field in all_fields}
                )
            )
        return out

    def add_objective(self, run_id: int, value: opt.Objective):
        if isinstance(value.target, opt.Metric):
            name = value.target.name
        else:
            name = str(value.target)
        self._execute_single(
            """
            INSERT INTO objectives (run_id, target, sense, scale, name, description, value_on_fail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                name,
                value.sense,
                value.scale,
                value.name,
                value.description,
                value.value_on_fail,
            ),
        )

    def get_objectives(self, run_id: int) -> list[opt.Objective]:
        rows = self._execute_single(
            """
            SELECT * FROM objectives WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
        out = []
        for row in rows:
            row = dict(row)
            all_fields = (field.name for field in fields(opt.Objective))
            out.append(opt.Objective(**{field: row[field] for field in all_fields}))
        return out

    def add_constraint(self, run_id: int, value: opt.Constraint) -> int:
        if isinstance(value.target, opt.Metric):
            name = value.target.name
        else:
            name = str(value.target)
        c = self._execute_single(
            """
            INSERT INTO constraints (run_id, target, lower, upper, name, scale, description, violation_on_fail, min_auto_scale)
            VALUES (:run_id, :target, :lower, :upper, :name, :scale, :description, :violation_on_fail, :min_auto_scale)
            """,
            {
                "run_id": run_id,
                "target": name,
                "lower": value.lower,
                "upper": value.upper,
                "name": value.name,
                "scale": value.scale,
                "description": value.description,
                "violation_on_fail": value.violation_on_fail,
                "min_auto_scale": value.min_auto_scale,
                "sanitized_scale": value.sanitized_scale,
            },
        )
        return c.lastrowid

    def get_constraints(self, run_id: int) -> list[opt.Constraint]:
        rows = self._execute_single(
            """
            SELECT * FROM constraints WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
        out = []
        for row in rows:
            row = dict(row)
            all_fields = (field.name for field in fields(opt.Constraint))
            out.append(opt.Constraint(**{field: row[field] for field in all_fields}))
        return out

    def add_iteration(
        self,
        run_id: int,
        iteration: int,
        objectives: dict[str, opt.ObjectiveResult] | None = None,
        constraints: dict[str, opt.ConstraintResult] | None = None,
        metrics: dict[str, opt.MetricResult] | None = None,
        metadata: str | None = None,
    ):
        if objectives is not None:
            objectives = json.dumps(
                {name: obj.to_dict() for name, obj in objectives.items()}
            )
        if constraints is not None:
            constraints = json.dumps(
                {name: constr.to_dict() for name, constr in constraints.items()}
            )
        if metrics is not None:
            metrics = json.dumps(
                {name: metric.to_dict() for name, metric in metrics.items()}
            )
        c = self._execute_single(
            """
            INSERT INTO iterations (run_id, iteration, objectives, constraints, metrics, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                iteration,
                objectives,
                constraints,
                metrics,
                str(metadata),
            ),
        )
        return c.lastrowid

    def get_last_iteration_number(self, run_id: int) -> int:
        row = self._execute_single(
            """
            SELECT MAX(iteration) as max_iter FROM iterations WHERE run_id = (?)
            """,
            (run_id,),
        ).fetchone()
        return row["max_iter"]

    def _sanitize_iteration_row(self, row: sqlite3.Row) -> Iteration:
        row = dict(row)
        if (obj := row["objectives"]) is not None:
            obj = json.loads(obj)
            obj = {
                name: opt.ObjectiveResult.from_dict(dct) for name, dct in obj.items()
            }
        if (constr := row["constraints"]) is not None:
            constr = json.loads(constr)
            constr = {
                name: opt.ConstraintResult.from_dict(dct)
                for name, dct in constr.items()
            }
        if (metrics := row["metrics"]) is not None:
            metrics = json.loads(metrics)
            metrics = {
                name: opt.MetricResult.from_dict(dct) for name, dct in metrics.items()
            }
        return Iteration(
            run_id=row["run_id"],
            iteration=row["iteration"],
            objectives=obj,
            constraints=constr,
            metrics=metrics,
        )

    def get_iteration(self, run_id: int, iteration: int = -1) -> Iteration:
        if iteration == -1:
            iteration = self.get_last_iteration_number(run_id)
        row = self._execute_single(
            """
            SELECT * FROM iterations WHERE run_id = (?) AND iteration = (?)
            """,
            (run_id, iteration),
        ).fetchone()
        return self._sanitize_iteration_row(row)

    def close(self):
        self.conn.close()
