"""esquema inicial

Revision ID: 0001
Revises: 
Create Date: 2026-10-05 22:28:59.549691
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('escalas_volumen',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cantidad_min', sa.Integer(), nullable=False),
    sa.Column('cantidad_max', sa.Integer(), nullable=True),
    sa.Column('descuento', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_escalas_volumen')),
    sa.UniqueConstraint('cantidad_min', name=op.f('uq_escalas_volumen_cantidad_min'))
    )
    op.create_table('margenes_categoria',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('categoria', sa.String(length=40), nullable=False),
    sa.Column('margen_minimo', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_margenes_categoria')),
    sa.UniqueConstraint('categoria', name=op.f('uq_margenes_categoria_categoria'))
    )
    op.create_table('niveles_canal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=30), nullable=False),
    sa.Column('descuento', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_niveles_canal')),
    sa.UniqueConstraint('nombre', name=op.f('uq_niveles_canal_nombre'))
    )
    op.create_table('parametros',
    sa.Column('clave', sa.String(length=60), nullable=False),
    sa.Column('valor', sa.String(length=120), nullable=False),
    sa.Column('descripcion', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('clave', name=op.f('pk_parametros'))
    )
    op.create_table('promociones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('referencia', sa.String(length=30), nullable=False),
    sa.Column('nombre', sa.String(length=160), nullable=False),
    sa.Column('descuento', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.Column('fecha_inicio', sa.Date(), nullable=False),
    sa.Column('fecha_fin', sa.Date(), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_promociones'))
    )
    op.create_index(op.f('ix_promociones_referencia'), 'promociones', ['referencia'], unique=False)
    op.create_table('usuarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario', sa.String(length=50), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=100), nullable=False),
    sa.Column('rol', sa.String(length=20), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usuarios')),
    sa.UniqueConstraint('usuario', name=op.f('uq_usuarios_usuario'))
    )
    op.create_table('canales',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nit', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=160), nullable=False),
    sa.Column('ciudad', sa.String(length=80), nullable=False),
    sa.Column('contacto_nombre', sa.String(length=120), nullable=False),
    sa.Column('contacto_email', sa.String(length=120), nullable=False),
    sa.Column('nivel_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['nivel_id'], ['niveles_canal.id'], name=op.f('fk_canales_nivel_id_niveles_canal')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_canales')),
    sa.UniqueConstraint('nit', name=op.f('uq_canales_nit'))
    )
    op.create_table('cotizaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.String(length=20), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('version_anterior_id', sa.Integer(), nullable=True),
    sa.Column('reemplazada', sa.Boolean(), nullable=False),
    sa.Column('canal_id', sa.Integer(), nullable=False),
    sa.Column('ejecutivo_id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=30), nullable=False),
    sa.Column('evaluacion', sa.String(length=30), nullable=True),
    sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('recibida_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('calculada_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('emitida_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('vigente_hasta', sa.DateTime(timezone=True), nullable=True),
    sa.Column('proximo_seguimiento_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cerrada_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pdf_ruta', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['canal_id'], ['canales.id'], name=op.f('fk_cotizaciones_canal_id_canales')),
    sa.ForeignKeyConstraint(['ejecutivo_id'], ['usuarios.id'], name=op.f('fk_cotizaciones_ejecutivo_id_usuarios')),
    sa.ForeignKeyConstraint(['version_anterior_id'], ['cotizaciones.id'], name=op.f('fk_cotizaciones_version_anterior_id_cotizaciones')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cotizaciones')),
    sa.UniqueConstraint('numero', 'version', name=op.f('uq_cotizaciones_numero'))
    )
    op.create_index(op.f('ix_cotizaciones_ejecutivo_id'), 'cotizaciones', ['ejecutivo_id'], unique=False)
    op.create_index(op.f('ix_cotizaciones_estado'), 'cotizaciones', ['estado'], unique=False)
    op.create_index(op.f('ix_cotizaciones_numero'), 'cotizaciones', ['numero'], unique=False)
    op.create_table('eventos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('cotizacion_id', sa.Integer(), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('ocurrido_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['cotizacion_id'], ['cotizaciones.id'], name=op.f('fk_eventos_cotizacion_id_cotizaciones')),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_eventos_usuario_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_eventos'))
    )
    op.create_index(op.f('ix_eventos_cotizacion_id'), 'eventos', ['cotizacion_id'], unique=False)
    op.create_index('ix_eventos_tipo_ocurrido_en', 'eventos', ['tipo', 'ocurrido_en'], unique=False)
    op.create_table('lineas_cotizacion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cotizacion_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('referencia', sa.String(length=30), nullable=False),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('descuento_adicional', sa.Numeric(precision=6, scale=4), nullable=False),
    sa.Column('descripcion', sa.String(length=255), nullable=True),
    sa.Column('categoria', sa.String(length=40), nullable=True),
    sa.Column('costo', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('precio_lista', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('precio_unitario', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('margen', sa.Numeric(precision=8, scale=4), nullable=True),
    sa.Column('margen_minimo', sa.Numeric(precision=6, scale=4), nullable=True),
    sa.Column('estado', sa.String(length=20), nullable=True),
    sa.Column('requiere_aprobacion', sa.Boolean(), nullable=False),
    sa.Column('bajo_pedido', sa.Boolean(), nullable=False),
    sa.Column('disponible', sa.Integer(), nullable=True),
    sa.Column('cantidad_comprometida', sa.Integer(), nullable=False),
    sa.Column('promocion_fin', sa.Date(), nullable=True),
    sa.Column('reglas_aplicadas', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['cotizacion_id'], ['cotizaciones.id'], name=op.f('fk_lineas_cotizacion_cotizacion_id_cotizaciones'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lineas_cotizacion'))
    )
    op.create_index(op.f('ix_lineas_cotizacion_cotizacion_id'), 'lineas_cotizacion', ['cotizacion_id'], unique=False)
    op.create_index(op.f('ix_lineas_cotizacion_referencia'), 'lineas_cotizacion', ['referencia'], unique=False)
    op.create_table('notificaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('cotizacion_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=40), nullable=False),
    sa.Column('mensaje', sa.String(length=500), nullable=False),
    sa.Column('leida', sa.Boolean(), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['cotizacion_id'], ['cotizaciones.id'], name=op.f('fk_notificaciones_cotizacion_id_cotizaciones')),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_notificaciones_usuario_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notificaciones'))
    )
    op.create_index(op.f('ix_notificaciones_usuario_id'), 'notificaciones', ['usuario_id'], unique=False)
    op.create_table('solicitudes_aprobacion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cotizacion_id', sa.Integer(), nullable=False),
    sa.Column('solicitante_id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('solicitada_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('vence_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('escalada', sa.Boolean(), nullable=False),
    sa.Column('escalada_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resuelta_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resuelta_por_id', sa.Integer(), nullable=True),
    sa.Column('comentario', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['cotizacion_id'], ['cotizaciones.id'], name=op.f('fk_solicitudes_aprobacion_cotizacion_id_cotizaciones')),
    sa.ForeignKeyConstraint(['resuelta_por_id'], ['usuarios.id'], name=op.f('fk_solicitudes_aprobacion_resuelta_por_id_usuarios')),
    sa.ForeignKeyConstraint(['solicitante_id'], ['usuarios.id'], name=op.f('fk_solicitudes_aprobacion_solicitante_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_solicitudes_aprobacion'))
    )
    op.create_index(op.f('ix_solicitudes_aprobacion_cotizacion_id'), 'solicitudes_aprobacion', ['cotizacion_id'], unique=False)
    op.create_index(op.f('ix_solicitudes_aprobacion_estado'), 'solicitudes_aprobacion', ['estado'], unique=False)
    op.create_table('tareas_seguimiento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cotizacion_id', sa.Integer(), nullable=False),
    sa.Column('ejecutivo_id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('creada_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('cerrada_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resultado', sa.String(length=20), nullable=True),
    sa.Column('nota', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['cotizacion_id'], ['cotizaciones.id'], name=op.f('fk_tareas_seguimiento_cotizacion_id_cotizaciones')),
    sa.ForeignKeyConstraint(['ejecutivo_id'], ['usuarios.id'], name=op.f('fk_tareas_seguimiento_ejecutivo_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tareas_seguimiento'))
    )
    op.create_index(op.f('ix_tareas_seguimiento_cotizacion_id'), 'tareas_seguimiento', ['cotizacion_id'], unique=False)
    op.create_index(op.f('ix_tareas_seguimiento_ejecutivo_id'), 'tareas_seguimiento', ['ejecutivo_id'], unique=False)
    op.create_index(op.f('ix_tareas_seguimiento_estado'), 'tareas_seguimiento', ['estado'], unique=False)

    # El registro de eventos es la pista de auditoría: solo admite inserciones.
    op.execute(
        """
        CREATE FUNCTION eventos_inmutables() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Los eventos son inmutables: no se permite % sobre la tabla eventos', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eventos_inmutables
        BEFORE UPDATE OR DELETE ON eventos
        FOR EACH ROW EXECUTE FUNCTION eventos_inmutables()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_eventos_inmutables ON eventos")
    op.execute("DROP FUNCTION eventos_inmutables()")
    op.drop_index(op.f('ix_tareas_seguimiento_estado'), table_name='tareas_seguimiento')
    op.drop_index(op.f('ix_tareas_seguimiento_ejecutivo_id'), table_name='tareas_seguimiento')
    op.drop_index(op.f('ix_tareas_seguimiento_cotizacion_id'), table_name='tareas_seguimiento')
    op.drop_table('tareas_seguimiento')
    op.drop_index(op.f('ix_solicitudes_aprobacion_estado'), table_name='solicitudes_aprobacion')
    op.drop_index(op.f('ix_solicitudes_aprobacion_cotizacion_id'), table_name='solicitudes_aprobacion')
    op.drop_table('solicitudes_aprobacion')
    op.drop_index(op.f('ix_notificaciones_usuario_id'), table_name='notificaciones')
    op.drop_table('notificaciones')
    op.drop_index(op.f('ix_lineas_cotizacion_referencia'), table_name='lineas_cotizacion')
    op.drop_index(op.f('ix_lineas_cotizacion_cotizacion_id'), table_name='lineas_cotizacion')
    op.drop_table('lineas_cotizacion')
    op.drop_index('ix_eventos_tipo_ocurrido_en', table_name='eventos')
    op.drop_index(op.f('ix_eventos_cotizacion_id'), table_name='eventos')
    op.drop_table('eventos')
    op.drop_index(op.f('ix_cotizaciones_numero'), table_name='cotizaciones')
    op.drop_index(op.f('ix_cotizaciones_estado'), table_name='cotizaciones')
    op.drop_index(op.f('ix_cotizaciones_ejecutivo_id'), table_name='cotizaciones')
    op.drop_table('cotizaciones')
    op.drop_table('canales')
    op.drop_table('usuarios')
    op.drop_index(op.f('ix_promociones_referencia'), table_name='promociones')
    op.drop_table('promociones')
    op.drop_table('parametros')
    op.drop_table('niveles_canal')
    op.drop_table('margenes_categoria')
    op.drop_table('escalas_volumen')
