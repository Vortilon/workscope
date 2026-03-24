"""add_aircraft_engine_type_tables

Revision ID: a4453a6bba16
Revises: 0304b25ca69e
Create Date: 2026-03-24 11:55:03.289031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4453a6bba16'
down_revision: Union[str, None] = '0304b25ca69e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('aircraft_types',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('manufacturer', sa.String(length=128), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('series', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_aircraft_types_manufacturer'), 'aircraft_types', ['manufacturer'], unique=False)
    op.create_index(op.f('ix_aircraft_types_model'), 'aircraft_types', ['model'], unique=False)

    op.create_table('engine_types',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('engine_family', sa.String(length=128), nullable=False),
        sa.Column('engine_model', sa.String(length=128), nullable=False),
        sa.Column('engine_manufacturer', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_engine_types_engine_family'), 'engine_types', ['engine_family'], unique=False)
    op.create_index(op.f('ix_engine_types_engine_manufacturer'), 'engine_types', ['engine_manufacturer'], unique=False)
    op.create_index(op.f('ix_engine_types_engine_model'), 'engine_types', ['engine_model'], unique=False)

    op.add_column('projects', sa.Column('aircraft_type_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('engine_type_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_projects_aircraft_type_id'), 'projects', ['aircraft_type_id'], unique=False)
    op.create_index(op.f('ix_projects_engine_type_id'), 'projects', ['engine_type_id'], unique=False)
    # FK via ALTER TABLE not supported by SQLite — enforced at application level.

    # ── Seed aircraft types (alphabetical by manufacturer, then model) ────────
    from datetime import datetime as _dt
    _now = _dt.utcnow()
    _at = sa.table('aircraft_types',
                   sa.column('manufacturer', sa.String),
                   sa.column('model', sa.String),
                   sa.column('series', sa.String),
                   sa.column('created_at', sa.DateTime))
    _aircraft = sorted([
        ("Airbus", "A220-300 (BD-500-1A11)", "A220-300"),
        ("Airbus", "A320-214", "A320-200"),
        ("Airbus", "A320-216", "A320-200"),
        ("Airbus", "A320-232", "A320-200"),
        ("Airbus", "A320-233", "A320-200"),
        ("Airbus", "A320-251N", "A320-NEO"),
        ("Airbus", "A320-271N", "A320-NEO"),
        ("Airbus", "A321-211", "A321-200"),
        ("Airbus", "A321-231", "A321-200"),
        ("Airbus", "A321-251N", "A321-NEO"),
        ("Airbus", "A321-251NX", "A321-NEO"),
        ("Airbus", "A321-253NX", "A321-NEO"),
        ("Airbus", "A321-271N", "A321-NEO"),
        ("Airbus", "A321-271NX", "A321-NEO"),
        ("Airbus", "A330-223", "A330-200"),
        ("Airbus", "A330-243", "A330-200"),
        ("Airbus", "A330-302", "A330-300"),
        ("Airbus", "A330-323", "A330-300"),
        ("Airbus", "A330-343", "A330-300"),
        ("Airbus", "A330-900NEO", "A330-900"),
        ("Airbus", "A330-941", "A330-900"),
        ("Airbus", "A350-941", "A350-900"),
        ("ATR", "ATR 42-500", "ATR 42"),
        ("ATR", "ATR 42-500 '600 version'", "ATR 42"),
        ("ATR", "ATR 72-212A", "ATR 72"),
        ("ATR", "ATR 72-212A '600 version'", "ATR 72"),
        ("Boeing", "737-700", "737-700"),
        ("Boeing", "737-800", "737-800"),
        ("Boeing", "737-8", "737-8"),
        ("Boeing", "737-9", "737-9"),
        ("Boeing", "737-900ER", "737-900ER"),
        ("Boeing", "777-300ER", "777-300ER"),
        ("Boeing", "777F", "777F"),
        ("Boeing", "787-8", "787-8"),
        ("Boeing", "787-9", "787-9"),
        ("De Havilland Canada", "DHC-8-400", "DHC-8-400"),
    ], key=lambda r: (r[0], r[1]))
    op.bulk_insert(_at, [
        {"manufacturer": m, "model": mo, "series": s, "created_at": _now}
        for m, mo, s in _aircraft
    ])

    # ── Seed engine types (alphabetical by manufacturer, family, model) ───────
    _et = sa.table('engine_types',
                   sa.column('engine_family', sa.String),
                   sa.column('engine_model', sa.String),
                   sa.column('engine_manufacturer', sa.String),
                   sa.column('created_at', sa.DateTime))
    _engines = sorted([
        ("CF34-10", "CF34-10E5", "General Electric"),
        ("CF34-10", "CF34-10E6", "General Electric"),
        ("CF34-10", "CF34-10E7", "General Electric"),
        ("CF6-80E", "CF6-80E1A4/B", "General Electric"),
        ("CFM LEAP", "LEAP-1A26", "CFM Industries"),
        ("CFM LEAP", "LEAP-1A32", "CFM Industries"),
        ("CFM LEAP", "LEAP-1A33", "CFM Industries"),
        ("CFM LEAP-1B", "LEAP-1B25", "CFM Industries"),
        ("CFM LEAP-1B", "LEAP-1B27", "CFM Industries"),
        ("CFM LEAP-1B", "LEAP-1B28", "CFM Industries"),
        ("CFM LEAP-1B", "LEAP-1B28B1", "CFM Industries"),
        ("CFM56-5", "CFM56-5B3/3", "CFM Industries"),
        ("CFM56-5", "CFM56-5B4/3", "CFM Industries"),
        ("CFM56-5", "CFM56-5B4/P", "CFM Industries"),
        ("CFM56-5", "CFM56-5B6/3", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B22", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B22/3", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B24", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B24/3", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B24E", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B26", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B26/3", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B26E", "CFM Industries"),
        ("CFM56-7B", "CFM56-7B27E", "CFM Industries"),
        ("GE90", "GE90-110B1L", "General Electric"),
        ("GE90", "GE90-115B", "General Electric"),
        ("GEnx", "GEnx-1B70/75/P2", "General Electric"),
        ("GEnx", "GEnx-1B74/75/P2", "General Electric"),
        ("PW 100", "PW127F", "Pratt & Whitney Canada"),
        ("PW 100", "PW127M", "Pratt & Whitney Canada"),
        ("PW 100", "PW127XT-M", "Pratt & Whitney Canada"),
        ("PW 100", "PW150A", "Pratt & Whitney Canada"),
        ("PW1000G", "PW1127G-JM", "Pratt & Whitney Canada"),
        ("PW1000G", "PW1127GA-JM", "Pratt & Whitney Canada"),
        ("PW1000G", "PW1133G-JM", "Pratt & Whitney Canada"),
        ("PW1000G", "PW1133GA-JM", "Pratt & Whitney Canada"),
        ("PW1000G", "PW1524G", "Pratt & Whitney Canada"),
        ("PW4000-100", "PW4168A", "Pratt & Whitney"),
        ("RR RB211 Trent 700", "RB211 TRENT 772B-60", "Rolls Royce"),
        ("RR Trent 1000", "Trent 1000-D2", "Rolls Royce"),
        ("RR Trent 1000", "Trent 1000-D3", "Rolls Royce"),
        ("RR Trent 7000", "Trent 7000", "Rolls Royce"),
        ("RR Trent XWB", "Trent XWB-84", "Rolls Royce"),
        ("V2500", "V2527-A5", "International Aero Engines"),
        ("V2500", "V2527-A5 Select One", "International Aero Engines"),
        ("V2500", "V2527-A5 Select Two", "International Aero Engines"),
        ("V2500", "V2527E-A5 Select Two", "International Aero Engines"),
        ("V2500", "V2533-A5", "International Aero Engines"),
        ("V2500", "V2533-A5 Select One", "International Aero Engines"),
        ("V2500", "V2533-A5 Select Two", "International Aero Engines"),
    ], key=lambda r: (r[2], r[0], r[1]))
    op.bulk_insert(_et, [
        {"engine_family": f, "engine_model": m, "engine_manufacturer": mfr, "created_at": _now}
        for f, m, mfr in _engines
    ])


def downgrade() -> None:
    op.drop_index(op.f('ix_projects_engine_type_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_aircraft_type_id'), table_name='projects')
    op.drop_column('projects', 'engine_type_id')
    op.drop_column('projects', 'aircraft_type_id')
    op.drop_index(op.f('ix_engine_types_engine_model'), table_name='engine_types')
    op.drop_index(op.f('ix_engine_types_engine_manufacturer'), table_name='engine_types')
    op.drop_index(op.f('ix_engine_types_engine_family'), table_name='engine_types')
    op.drop_table('engine_types')
    op.drop_index(op.f('ix_aircraft_types_model'), table_name='aircraft_types')
    op.drop_index(op.f('ix_aircraft_types_manufacturer'), table_name='aircraft_types')
    op.drop_table('aircraft_types')
