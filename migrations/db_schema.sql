-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.challenges (
  id integer NOT NULL DEFAULT nextval('challenges_id_seq'::regclass),
  name character varying NOT NULL,
  category character varying NOT NULL,
  difficulty character varying DEFAULT 'Medium'::character varying,
  description text,
  points integer DEFAULT 100,
  flag text,
  setter character varying,
  status character varying DEFAULT 'pending'::character varying,
  pr_number integer,
  branch character varying,
  ctfd_id integer,
  pushed_to_ctfd boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  hint text,
  solution text,
  round_id integer,
  CONSTRAINT challenges_pkey PRIMARY KEY (id),
  CONSTRAINT challenges_round_id_fkey FOREIGN KEY (round_id) REFERENCES public.rounds(id)
);
CREATE TABLE public.ctfd_team_credentials (
  id bigint NOT NULL DEFAULT nextval('ctfd_team_credentials_id_seq'::regclass),
  team_id bigint,
  ctfd_team_id bigint UNIQUE,
  ctfd_team_password text,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT ctfd_team_credentials_pkey PRIMARY KEY (id),
  CONSTRAINT ctfd_team_credentials_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(registration_id)
);
CREATE TABLE public.ctfd_user_credentials (
  id bigint NOT NULL DEFAULT nextval('ctfd_user_credentials_id_seq'::regclass),
  member_id bigint,
  ctfd_user_id bigint UNIQUE,
  ctfd_password text,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT ctfd_user_credentials_pkey PRIMARY KEY (id),
  CONSTRAINT ctfd_user_credentials_member_id_fkey FOREIGN KEY (member_id) REFERENCES public.team_members(id)
);
CREATE TABLE public.email_attachments (
  id integer NOT NULL DEFAULT nextval('email_attachments_id_seq'::regclass),
  original_filename character varying NOT NULL,
  stored_filename character varying NOT NULL UNIQUE,
  file_size integer NOT NULL DEFAULT 0,
  mime_type character varying DEFAULT 'application/octet-stream'::character varying,
  is_image boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT email_attachments_pkey PRIMARY KEY (id)
);
CREATE TABLE public.email_audit_logs (
  id integer NOT NULL DEFAULT nextval('email_audit_logs_id_seq'::regclass),
  template_id integer,
  template_name character varying,
  recipient_email character varying NOT NULL,
  recipient_name character varying,
  team_id integer,
  team_name character varying,
  status character varying NOT NULL DEFAULT 'sent'::character varying CHECK (status::text = ANY (ARRAY['sent'::character varying, 'failed'::character varying]::text[])),
  error_message text,
  sent_at timestamp with time zone DEFAULT now(),
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT email_audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT email_audit_logs_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.email_templates(id),
  CONSTRAINT email_audit_logs_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id)
);
CREATE TABLE public.email_templates (
  id integer NOT NULL DEFAULT nextval('email_templates_id_seq'::regclass),
  name character varying NOT NULL UNIQUE,
  subject character varying NOT NULL,
  body text NOT NULL,
  description text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT email_templates_pkey PRIMARY KEY (id)
);
CREATE TABLE public.rounds (
  id integer NOT NULL DEFAULT nextval('rounds_id_seq'::regclass),
  name character varying NOT NULL,
  description text,
  created_at timestamp with time zone DEFAULT now(),
  start_datetime timestamp with time zone,
  timezone character varying DEFAULT 'UTC'::character varying,
  CONSTRAINT rounds_pkey PRIMARY KEY (id)
);
CREATE TABLE public.settings (
  id integer NOT NULL DEFAULT nextval('settings_id_seq'::regclass),
  key character varying NOT NULL UNIQUE,
  value text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT settings_pkey PRIMARY KEY (id)
);
CREATE TABLE public.targets (
  id integer NOT NULL DEFAULT nextval('targets_id_seq'::regclass),
  category character varying NOT NULL,
  difficulty character varying NOT NULL,
  target_count integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  round_id integer,
  CONSTRAINT targets_pkey PRIMARY KEY (id),
  CONSTRAINT targets_round_id_fkey FOREIGN KEY (round_id) REFERENCES public.rounds(id)
);
CREATE TABLE public.team_members (
  id bigint NOT NULL DEFAULT nextval('team_members_id_seq'::regclass),
  team_id bigint,
  name text,
  full_name text,
  class text,
  institution text,
  email character varying,
  phone character varying,
  gender character varying,
  address text,
  father_name character varying,
  father_number character varying,
  t_shirt_size character varying,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT team_members_pkey PRIMARY KEY (id),
  CONSTRAINT team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(registration_id)
);
CREATE TABLE public.teams (
  id bigint NOT NULL DEFAULT nextval('teams_id_seq'::regclass),
  registration_id bigint UNIQUE,
  team_name character varying NOT NULL,
  captain_name character varying,
  captain_email character varying,
  contact_number character varying,
  status character varying DEFAULT 'pending'::character varying,
  created_at timestamp without time zone DEFAULT now(),
  updated_at timestamp without time zone DEFAULT now(),
  CONSTRAINT teams_pkey PRIMARY KEY (id)
);
