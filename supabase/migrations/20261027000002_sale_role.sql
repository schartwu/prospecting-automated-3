-- KG Lead (2026-10-27): DV's sales team uses the web app too. Roles: dv and sale update statuses; viewer
-- (AVP, GM, the monitor team) only looks.
alter table lead_users drop constraint lead_users_role_check;
alter table lead_users add constraint lead_users_role_check check (role in ('dv', 'sale', 'viewer'));
