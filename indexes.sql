-- ============================================================================
-- INDEXES FOR ROUPA DE GALA DATABASE
-- Run: psql -U <user> -d <database> -f indexes.sql
-- All indexes use CREATE INDEX IF NOT EXISTS to be safe for re-runs
-- ============================================================================

-- ============================================================================
-- TIER 1: SERVICE_ORDERS — Critical compound indexes (dashboard, reports)
-- ============================================================================

-- Main filtering: is_virtual + order_date + phase (used in dashboard, planilha, finance)
CREATE INDEX IF NOT EXISTS idx_so_virtual_date_phase
ON service_orders (is_virtual, order_date, service_order_phase_id);

-- Employee/attendant dashboard metrics
CREATE INDEX IF NOT EXISTS idx_so_employee_date_phase
ON service_orders (employee_id, order_date, service_order_phase_id);

CREATE INDEX IF NOT EXISTS idx_so_attendant_date
ON service_orders (attendant_id, order_date);

-- Renter filtering (client OS history)
CREATE INDEX IF NOT EXISTS idx_so_renter_virtual
ON service_orders (renter_id, is_virtual);

-- ============================================================================
-- TIER 2: SERVICE_ORDERS — Date fields (status calculations, overdue checks)
-- ============================================================================

-- Date range filtering (20+ uses across views)
CREATE INDEX IF NOT EXISTS idx_so_order_date
ON service_orders (order_date);

-- Status/agenda calculations (prova, retirada, devolucao)
CREATE INDEX IF NOT EXISTS idx_so_prova_phase
ON service_orders (prova_date, service_order_phase_id);

CREATE INDEX IF NOT EXISTS idx_so_retirada_phase
ON service_orders (retirada_date, service_order_phase_id);

CREATE INDEX IF NOT EXISTS idx_so_devolucao_phase_devolvido
ON service_orders (devolucao_date, service_order_phase_id, data_devolvido);

-- Overdue detection (event date + phase)
CREATE INDEX IF NOT EXISTS idx_so_event_phase
ON service_orders (event_id, service_order_phase_id);

-- ============================================================================
-- TIER 3: SERVICE_ORDERS — Single field indexes (high-frequency lookups)
-- ============================================================================

-- Phase filtering (80+ filter calls)
CREATE INDEX IF NOT EXISTS idx_so_phase
ON service_orders (service_order_phase_id);

-- Default ordering (-order_date, -id)
CREATE INDEX IF NOT EXISTS idx_so_date_id_desc
ON service_orders (order_date DESC, id DESC);

-- Origin channel filtering/grouping (planilha, dashboard)
CREATE INDEX IF NOT EXISTS idx_so_came_from
ON service_orders (came_from);

-- Late flag
CREATE INDEX IF NOT EXISTS idx_so_atrasada
ON service_orders (esta_atrasada)
WHERE esta_atrasada = true;

-- Virtual orders (finance endpoint)
CREATE INDEX IF NOT EXISTS idx_so_virtual
ON service_orders (is_virtual)
WHERE is_virtual = true;

-- Finalized date (FINALIZADO tab filtering)
CREATE INDEX IF NOT EXISTS idx_so_data_finalizado
ON service_orders (data_finalizado);

-- Refused date (RECUSADA tab filtering)
CREATE INDEX IF NOT EXISTS idx_so_data_recusa
ON service_orders (data_recusa);

-- Production date (EM_PRODUCAO tab filtering)
CREATE INDEX IF NOT EXISTS idx_so_production_date
ON service_orders (production_date);

-- ============================================================================
-- TIER 4: PERSONS_CONTACTS — Recent contact lookups (6+ uses)
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_contacts_person_recent
ON persons_contacts (person_id, date_created DESC, id DESC);

-- Text search on contacts
CREATE INDEX IF NOT EXISTS idx_contacts_phone
ON persons_contacts (phone);

CREATE INDEX IF NOT EXISTS idx_contacts_email
ON persons_contacts (email);

-- ============================================================================
-- TIER 5: PERSONS_ADRESSES — Recent address lookups (5+ uses)
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_addresses_person_recent
ON persons_adresses (person_id, date_created DESC, id DESC);

-- ============================================================================
-- TIER 6: PERSON — Search and filtering
-- ============================================================================

-- Person type filtering (CLIENTE, ADMINISTRADOR, ATENDENTE)
CREATE INDEX IF NOT EXISTS idx_person_type
ON person (person_type_id);

-- Name search (icontains — trigram index for LIKE queries)
CREATE INDEX IF NOT EXISTS idx_person_name_trgm
ON person USING gin (name gin_trgm_ops);

-- CPF lookup (already unique, but verify)
-- Person.cpf has unique=True which creates an implicit index

-- ============================================================================
-- TIER 7: PRODUCTS — Dashboard counts and filtering
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_product_tipo
ON products (tipo);

CREATE INDEX IF NOT EXISTS idx_product_marca
ON products (marca);

-- Product name search
CREATE INDEX IF NOT EXISTS idx_product_nome_trgm
ON products USING gin (nome_produto gin_trgm_ops);

-- ============================================================================
-- TIER 8: SERVICE_ORDER_ITEMS — Join optimization
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_soi_service_order
ON service_order_items (service_order_id);

CREATE INDEX IF NOT EXISTS idx_soi_temp_product
ON service_order_items (temporary_product_id);

CREATE INDEX IF NOT EXISTS idx_soi_product
ON service_order_items (product_id);

-- ============================================================================
-- TIER 9: EVENTS — Filtering
-- ============================================================================

-- Event date for overdue checks
CREATE INDEX IF NOT EXISTS idx_event_date
ON events (event_date);

-- ============================================================================
-- TIER 10: SERVICE_ORDER_PHASE — Name lookup
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_phase_name
ON service_control_serviceorderphase (name);

-- ============================================================================
-- IMPORTANT: Trigram indexes (gin_trgm_ops) require the pg_trgm extension.
-- Uncomment and run the line below FIRST if you want text search indexes:
-- ============================================================================
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
--
-- Then uncomment the trigram indexes above (idx_person_name_trgm,
-- idx_product_nome_trgm) for faster LIKE/ILIKE text searches.
-- If you don't need those, the rest of the file works without pg_trgm.
-- ============================================================================

-- ============================================================================
-- TABLE NAME REFERENCE (Django db_table mappings):
--   ServiceOrder         -> service_orders
--   ServiceOrderItem     -> service_order_items
--   ServiceOrderPhase    -> service_control_serviceorderphase
--   Person               -> person
--   PersonsContacts      -> persons_contacts
--   PersonsAdresses      -> persons_adresses
--   Product              -> products
--   Event                -> events
--   City                 -> city
--   PersonType           -> person_type
-- ============================================================================
