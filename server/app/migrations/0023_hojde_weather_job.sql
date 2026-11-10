-- Højde: the weather rule runs every hour (app/hojde/ops.py, job hojde.weather). A planned flight in the next 48 hours
-- with wind over 10 m/s or precipitation goes on vejrforbehold; one whose forecast cleared goes back.

insert into job_schedules (name, kind, description, interval_seconds) values
    ('hojde.weather', 'hojde.weather', 'Højde: sætter flyvninger de næste 48 timer på vejrforbehold eller ophæver det', 3600);
