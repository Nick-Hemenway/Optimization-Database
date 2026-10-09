import sqlite3
from dataclasses import dataclass
from pathlib import Path

import optwrap as opt
from optwrap.common import MISSING


@dataclass
class Run:
    run_id: int
    name: str
    parameters: opt.Parameters
    operating_points: opt.OperatingPoints


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
                    parameters TEXT,
                    operating_points TEXT,
                    description TEXT
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );         
                CREATE TABLE IF NOT EXISTS iterations (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    iteration_number INTEGER,
                    designs TEXT,
                    metrics TEXT,
                    cv TEXT,
                    cv_scaled TEXT,
                    objectives TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
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
                CREATE TABLE IF NOT EXISTS objectives (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    metric_name TEXT,
                    sense TEXT,
                    scale REAL,
                    description TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS constraints (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    metric_name TEXT,
                    lower REAL,
                    upper REAL,
                    scale REAL,
                    description TEXT,
                    cv_on_fail REAL,
                    min_auto_scale REAL,
                    sanitized_scale REAL,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                """
            )
            self.conn.execute("PRAGMA user_version = 1")

    def get_runs(self) -> list[Run]:
        with self.conn:
            rows = self.conn.execute("SELECT * FROM runs ORDER BY id ASC").fetchall()
        return [self._sanitize_run_output(row) for row in rows]

    def get_run(self, run_id: int) -> Run:
        with self.conn:
            row = self.conn.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._sanitize_run_output(row)

    def _sanitize_run_output(self, row: sqlite3.Row) -> Run:
        row = dict(row)
        if row["operating_points"] is not None:
            row["operating_points"] = opt.OperatingPoints.from_json(
                row["operating_points"]
            )
        if row["parameters"] is not None:
            row["parameters"] = opt.Parameters.from_json(row["parameters"])
        return Run(
            run_id=row["id"],
            name=row["name"],
            parameters=row["parameters"],
            operating_points=row["operating_points"],
        )

    def add_run(
        self,
        name: str,
        parameters: opt.Parameters | None = None,
        operating_points: opt.OperatingPoints | None = None,
        description: str | None = None,
    ) -> int:
        if operating_points is not None:
            op = operating_points.to_json()
        else:
            op = None
        if parameters is not None:
            parameters = parameters.to_json()
        with self.conn:
            c = self.conn.cursor()
            c.execute(
                """
                INSERT INTO runs (name, parameters, operating_points, description)
                VALUES (?, ?, ?, ?)
                """,
                (name, parameters, op, description),
            )
        return c.lastrowid

    def add_variable(self, run_id: int, value: opt.registry.Variable):
        if value.default is MISSING:
            default = None
        else:
            default = value.default
        with self.conn:
            self.conn.execute(
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
                    "default_value": default,
                },
            )

    def add_parameter(self, run_id: int, value: opt.Parameter):
        if value.default is MISSING:
            default = None
        else:
            default = value.default
        with self.conn:
            self.conn.execute(
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
                    "default_value": default,
                },
            )

    def get_variables(self, run_id: int) -> list[opt.Parameter]:
        with self.conn:
            rows = self.conn.execute(
                """
                SELECT * FROM variables WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        out = []
        for row in rows:
            if (default := row["default_value"]) is None:
                default = MISSING
            out.append(
                opt.registry.Variable(
                    name=row["name"],
                    start=row["start"],
                    size=row["size"],
                    lower=row["lower"],
                    upper=row["upper"],
                    units=row["units"],
                    description=row["description"],
                    label=row["label"],
                    scaling=row["scaling"],
                    default=default,
                )
            )
        return out

    def get_parameters(self, run_id: int) -> list[opt.Parameter]:
        with self.conn:
            rows = self.conn.execute(
                """
                SELECT * FROM parameters WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        out = []
        for row in rows:
            if (default := row["default_value"]) is None:
                default = MISSING
            out.append(
                opt.Parameter(
                    name=row["name"],
                    units=row["units"],
                    description=row["description"],
                    label=row["label"],
                    default=default,
                )
            )
        return out

    def get_operating_point_parameters(
        self, run_id: int
    ) -> list[opt.OperatingPointParameter]:
        with self.conn:
            rows = self.conn.execute(
                """
                SELECT * FROM operating_point_parameters WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        out = []
        for row in rows:
            if (default := row["default_value"]) is None:
                default = MISSING
            out.append(
                opt.OperatingPointParameter(
                    name=row["name"],
                    units=row["units"],
                    description=row["description"],
                    label=row["label"],
                    default=default,
                )
            )
        return out

    def add_operating_point_parameter(
        self, run_id: int, value: opt.OperatingPointParameter
    ):
        if value.default is MISSING:
            default = None
        else:
            default = value.default
        with self.conn:
            self.conn.execute(
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
                    "default_value": default,
                },
            )

    def add_objective(self, run_id: int, value: opt.Objective):
        if isinstance(value.metric, opt.Metric):
            name = value.metric.name
        else:
            name = str(value.metric)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO objectives (run_id, metric_name, sense, scale, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, name, value.sense, value.scale, value.description),
            )

    def add_constraint(self, run_id: int, value: opt.Constraint):
        if isinstance(value.metric, opt.Metric):
            name = value.metric.name
        else:
            name = str(value.metric)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO constraints (run_id, metric_name, lower, upper, scale, description, cv_on_fail, min_auto_scale, sanitized_scale)
                VALUES (:run_id, :metric_name, :lower, :upper, :scale, :description, :cv_on_fail, :min_auto_scale, :sanitized_scale)
                """,
                {
                    "run_id": run_id,
                    "metric_name": name,
                    "lower": value.lower,
                    "upper": value.upper,
                    "scale": value.scale,
                    "description": value.description,
                    "cv_on_fail": value.cv_on_fail,
                    "min_auto_scale": value.min_auto_scale,
                    "sanitized_scale": value.sanitized_scale,
                },
            )

    def close(self):
        self.conn.close()
