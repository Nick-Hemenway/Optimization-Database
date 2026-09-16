CREATE VIEW IF NOT EXISTS param_view AS
SELECT
d.id as design_id,
vp.name as parameter_name,
vpv.value as parameter_value,
vp.unit,
vp.label 
FROM variable_param_value vpv 
JOIN design d on vpv.design_id = d.id
JOIN variable_param vp on vpv.param_id = vp.id
ORDER BY design_id, parameter_name;


CREATE VIEW IF NOT EXISTS metric_view AS
SELECT
d.id as design_id,
m.name as metric_name,
mv.value as metric_value,
m.unit, m.label, m.id as metric_id
FROM metric_value mv 
JOIN design d ON mv.design_id = d.id
JOIN metric m ON mv.metric_id = m.id
ORDER BY design_id, metric_name;


CREATE VIEW IF NOT EXISTS objective_view AS
SELECT
mv.design_id, mv.metric_name,
mv.metric_value*o.sign as objective_value,
o.sign, mv.unit, mv.label, mv.metric_id
FROM objective o
JOIN metric_view mv on o.metric_id = mv.metric_id;


CREATE VIEW IF NOT EXISTS constraint_view AS
SELECT
mv.design_id, mv.metric_name,
mv.metric_value, c.lower_bound, c.upper_bound,
mv.unit, mv.label, mv.metric_id
FROM "constraint" c
JOIN metric_view mv on c.metric_id = mv.metric_id;


CREATE VIEW IF NOT EXISTS population_evolution_intermediate_view AS
SELECT
r.start_time as run_start_time,
r.id as run_id,
g.id as generation_id,
g.number as generation_number,
psm.design_id,
g1.number as generation_created
FROM post_selection_member psm
JOIN generation g ON psm.generation_id = g.id
JOIN run r ON g.run_id = r.id
JOIN design d on psm.design_id = d.id
JOIN generation g1 on d.generation_id = g1.id
ORDER BY run_start_time DESC, generation_number;


CREATE VIEW IF NOT EXISTS population_evolution_view AS
SELECT
peiv.*,
mv.metric_name, mv.metric_value, mv.unit, mv.label, mv.metric_id,
o.sign, o.sign*mv.metric_value as objective_value, o.id as objective_id,
c.lower_bound, c.upper_bound, c.id as constraint_id
FROM population_evolution_intermediate_view peiv
JOIN metric_view mv ON peiv.design_id = mv.design_id
LEFT JOIN objective o ON o.metric_id = mv.metric_id
LEFT JOIN "constraint" c ON c.metric_id = mv.metric_id;

CREATE VIEW IF NOT EXISTS designs_view AS
SELECT
r.id as run_id,
g.id as gen_id,
g.number as gen_number,
d.id as design_id,
d.number as design_number,
vp.name as param_name,
vpv.value as param_value
FROM run r
JOIN generation g ON g.run_id = r.id
JOIN design d ON d.generation_id = g.id
JOIN variable_param_value vpv ON vpv.design_id = d.id
JOIN variable_param vp ON vp.id = vpv.param_id
ORDER BY run_id, gen_number, design_id, vp.id;