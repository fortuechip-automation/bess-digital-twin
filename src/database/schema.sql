--
-- PostgreSQL database dump
--

\restrict jonsGNUJxnUvVylSLl7F6Mji9V4GvKCjzG96ZoS7Jm8h9HmnkhIe4cKTyy8Vf8U

-- Dumped from database version 14.22 (Ubuntu 14.22-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.22 (Ubuntu 14.22-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA public;


ALTER SCHEMA public OWNER TO postgres;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: bess_telemetry; Type: TABLE; Schema: public; Owner: bessuser
--

CREATE TABLE public.bess_telemetry (
    ts timestamp with time zone NOT NULL,
    soc_pct real NOT NULL,
    p_actual_kw real NOT NULL,
    v_dc_bus real,
    current_a real,
    temp_c real,
    mode_id smallint NOT NULL
);


ALTER TABLE public.bess_telemetry OWNER TO bessuser;

--
-- Name: battery_status; Type: TABLE; Schema: public; Owner: bessuser
--

CREATE TABLE public.battery_status (
    ts timestamp with time zone DEFAULT now() NOT NULL,
    battery_id integer NOT NULL,
    soc real NOT NULL,
    vdc real NOT NULL,
    idc real NOT NULL,
    p_dc_kw real NOT NULL,
    temp_c real NOT NULL,
    fault boolean DEFAULT false NOT NULL
);


ALTER TABLE public.battery_status OWNER TO bessuser;

--
-- Name: bess_alarms; Type: TABLE; Schema: public; Owner: bessuser
--

CREATE TABLE public.bess_alarms (
    alarm_id integer NOT NULL,
    ts timestamp with time zone DEFAULT now(),
    alarm_code text NOT NULL,
    severity smallint NOT NULL,
    message text,
    value real,
    threshold real,
    cleared boolean DEFAULT false,
    cleared_ts timestamp with time zone
);


ALTER TABLE public.bess_alarms OWNER TO bessuser;

--
-- Name: bess_alarms_alarm_id_seq; Type: SEQUENCE; Schema: public; Owner: bessuser
--

CREATE SEQUENCE public.bess_alarms_alarm_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.bess_alarms_alarm_id_seq OWNER TO bessuser;

--
-- Name: bess_alarms_alarm_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bessuser
--

ALTER SEQUENCE public.bess_alarms_alarm_id_seq OWNED BY public.bess_alarms.alarm_id;


--
-- Name: bess_commands; Type: TABLE; Schema: public; Owner: bessuser
--

CREATE TABLE public.bess_commands (
    command_id integer NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    p_set_kw real NOT NULL,
    mode_set character varying(50) NOT NULL,
    priority smallint DEFAULT 1,
    source_ip inet,
    processed boolean DEFAULT false
);


ALTER TABLE public.bess_commands OWNER TO bessuser;

--
-- Name: bess_commands_command_id_seq; Type: SEQUENCE; Schema: public; Owner: bessuser
--

CREATE SEQUENCE public.bess_commands_command_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.bess_commands_command_id_seq OWNER TO bessuser;

--
-- Name: bess_commands_command_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bessuser
--

ALTER SEQUENCE public.bess_commands_command_id_seq OWNED BY public.bess_commands.command_id;


--
-- Name: bess_status; Type: TABLE; Schema: public; Owner: bessuser
--

CREATE TABLE public.bess_status (
    id integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    soc numeric(6,2),
    power_kw numeric(10,2),
    current numeric(10,2),
    status text,
    voltage numeric(10,2),
    temperature numeric
);


ALTER TABLE public.bess_status OWNER TO bessuser;

--
-- Name: bess_status_id_seq; Type: SEQUENCE; Schema: public; Owner: bessuser
--

CREATE SEQUENCE public.bess_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.bess_status_id_seq OWNER TO bessuser;

--
-- Name: bess_status_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: bessuser
--

ALTER SEQUENCE public.bess_status_id_seq OWNED BY public.bess_status.id;


--
-- Name: ems_decisions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ems_decisions (
    decision_id integer NOT NULL,
    ts timestamp with time zone NOT NULL,
    command_fk integer,
    current_soc real NOT NULL,
    target_soc real,
    reasoning text NOT NULL
);


ALTER TABLE public.ems_decisions OWNER TO postgres;

--
-- Name: ems_decisions_decision_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ems_decisions_decision_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ems_decisions_decision_id_seq OWNER TO postgres;

--
-- Name: ems_decisions_decision_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ems_decisions_decision_id_seq OWNED BY public.ems_decisions.decision_id;


--
-- Name: inverter_status; Type: TABLE; Schema: public; Owner: bessuser
--

CREATE TABLE public.inverter_status (
    ts timestamp with time zone DEFAULT now() NOT NULL,
    inverter_id integer NOT NULL,
    mode smallint NOT NULL,
    p_set_kw real NOT NULL,
    p_actual_kw real NOT NULL,
    vdc real NOT NULL,
    idc real NOT NULL,
    temp_c real NOT NULL,
    fault boolean DEFAULT false NOT NULL
);


ALTER TABLE public.inverter_status OWNER TO bessuser;

--
-- Name: site_status; Type: TABLE; Schema: public; Owner: bessuser
--

CREATE TABLE public.site_status (
    ts timestamp with time zone DEFAULT now() NOT NULL,
    soc real NOT NULL,
    mode smallint NOT NULL,
    p_set_kw real NOT NULL,
    p_actual_kw real NOT NULL,
    vdc real NOT NULL,
    idc real NOT NULL,
    temp_c real NOT NULL,
    active_alarms integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.site_status OWNER TO bessuser;

--
-- Name: system_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.system_events (
    event_id integer NOT NULL,
    ts timestamp with time zone NOT NULL,
    source character varying(50) NOT NULL,
    event_level character varying(10) NOT NULL,
    message text NOT NULL,
    acknowledged boolean DEFAULT false
);


ALTER TABLE public.system_events OWNER TO postgres;

--
-- Name: system_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.system_events_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.system_events_event_id_seq OWNER TO postgres;

--
-- Name: system_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.system_events_event_id_seq OWNED BY public.system_events.event_id;


--
-- Name: bess_alarms alarm_id; Type: DEFAULT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.bess_alarms ALTER COLUMN alarm_id SET DEFAULT nextval('public.bess_alarms_alarm_id_seq'::regclass);


--
-- Name: bess_commands command_id; Type: DEFAULT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.bess_commands ALTER COLUMN command_id SET DEFAULT nextval('public.bess_commands_command_id_seq'::regclass);


--
-- Name: bess_status id; Type: DEFAULT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.bess_status ALTER COLUMN id SET DEFAULT nextval('public.bess_status_id_seq'::regclass);


--
-- Name: ems_decisions decision_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ems_decisions ALTER COLUMN decision_id SET DEFAULT nextval('public.ems_decisions_decision_id_seq'::regclass);


--
-- Name: system_events event_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_events ALTER COLUMN event_id SET DEFAULT nextval('public.system_events_event_id_seq'::regclass);


--
-- Name: battery_status battery_status_pkey; Type: CONSTRAINT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.battery_status
    ADD CONSTRAINT battery_status_pkey PRIMARY KEY (ts, battery_id);


--
-- Name: bess_alarms bess_alarms_pkey; Type: CONSTRAINT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.bess_alarms
    ADD CONSTRAINT bess_alarms_pkey PRIMARY KEY (alarm_id);


--
-- Name: bess_commands bess_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.bess_commands
    ADD CONSTRAINT bess_commands_pkey PRIMARY KEY (command_id);


--
-- Name: bess_status bess_status_pkey; Type: CONSTRAINT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.bess_status
    ADD CONSTRAINT bess_status_pkey PRIMARY KEY (id);


--
-- Name: ems_decisions ems_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ems_decisions
    ADD CONSTRAINT ems_decisions_pkey PRIMARY KEY (decision_id);


--
-- Name: inverter_status inverter_status_pkey; Type: CONSTRAINT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.inverter_status
    ADD CONSTRAINT inverter_status_pkey PRIMARY KEY (ts, inverter_id);


--
-- Name: site_status site_status_pkey; Type: CONSTRAINT; Schema: public; Owner: bessuser
--

ALTER TABLE ONLY public.site_status
    ADD CONSTRAINT site_status_pkey PRIMARY KEY (ts);


--
-- Name: system_events system_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_events
    ADD CONSTRAINT system_events_pkey PRIMARY KEY (event_id);


--
-- Name: bess_telemetry_ts_idx; Type: INDEX; Schema: public; Owner: bessuser
--

CREATE INDEX bess_telemetry_ts_idx ON public.bess_telemetry USING btree (ts DESC);


--
-- Name: idx_battery_status_latest; Type: INDEX; Schema: public; Owner: bessuser
--

CREATE INDEX idx_battery_status_latest ON public.battery_status USING btree (battery_id, ts DESC);


--
-- Name: idx_bess_alarms_active; Type: INDEX; Schema: public; Owner: bessuser
--

CREATE INDEX idx_bess_alarms_active ON public.bess_alarms USING btree (cleared) WHERE (cleared = false);


--
-- Name: idx_bess_alarms_code; Type: INDEX; Schema: public; Owner: bessuser
--

CREATE INDEX idx_bess_alarms_code ON public.bess_alarms USING btree (alarm_code);


--
-- Name: idx_bess_alarms_ts; Type: INDEX; Schema: public; Owner: bessuser
--

CREATE INDEX idx_bess_alarms_ts ON public.bess_alarms USING btree (ts);


--
-- Name: idx_inverter_status_latest; Type: INDEX; Schema: public; Owner: bessuser
--

CREATE INDEX idx_inverter_status_latest ON public.inverter_status USING btree (inverter_id, ts DESC);


--
-- Name: idx_site_status_latest; Type: INDEX; Schema: public; Owner: bessuser
--

CREATE INDEX idx_site_status_latest ON public.site_status USING btree (ts DESC);


--
-- Name: bess_telemetry ts_insert_blocker; Type: TRIGGER; Schema: public; Owner: bessuser
--

CREATE TRIGGER ts_insert_blocker BEFORE INSERT ON public.bess_telemetry FOR EACH ROW EXECUTE FUNCTION _timescaledb_functions.insert_blocker();


--
-- Name: ems_decisions ems_decisions_command_fk_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ems_decisions
    ADD CONSTRAINT ems_decisions_command_fk_fkey FOREIGN KEY (command_fk) REFERENCES public.bess_commands(command_id);


--
-- Name: TABLE ems_decisions; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.ems_decisions TO bessuser;


--
-- Name: SEQUENCE ems_decisions_decision_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.ems_decisions_decision_id_seq TO bessuser;


--
-- Name: TABLE system_events; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.system_events TO bessuser;


--
-- Name: SEQUENCE system_events_event_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.system_events_event_id_seq TO bessuser;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES  TO bessuser;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES  TO bessuser;


--
-- PostgreSQL database dump complete
--

\unrestrict jonsGNUJxnUvVylSLl7F6Mji9V4GvKCjzG96ZoS7Jm8h9HmnkhIe4cKTyy8Vf8U

