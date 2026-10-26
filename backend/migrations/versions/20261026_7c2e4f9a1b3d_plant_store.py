"""online plant store: products, orders and their bills

Revision ID: 7c2e4f9a1b3d
Revises: 3850def6ec20
Create Date: 2026-10-26 14:30:00

The catalogue starts with placeholder plants (names, prices and pictures to be replaced
from the office's Store products page).
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models.base


# revision identifiers, used by Alembic.
revision: str = "7c2e4f9a1b3d"
down_revision: Union[str, Sequence[str], None] = "3850def6ec20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _stamps():
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
    ]


# slug, name, botanical name, category, price, mrp, summary, description, care
PLANTS = [
    (
        "money-plant",
        "Money Plant",
        "Epipremnum aureum",
        "indoor",
        249,
        299,
        "The easiest trailing plant for a shelf, window or balcony grille.",
        "A fast-growing climber with glossy heart-shaped leaves. It forgives missed waterings, grows in bright shade or in a jar of water, and trails beautifully from a shelf. A good first plant for a new home.",
        {
            "light": "Bright indirect light; tolerates shade",
            "water": "When the top 2 cm of soil is dry",
            "size": "About 30 cm with trails",
            "pot": "6 inch nursery pot",
            "care_level": "Very easy",
            "pet_safe": False,
        },
    ),
    (
        "snake-plant",
        "Snake Plant",
        "Dracaena trifasciata",
        "indoor",
        349,
        399,
        "Upright, architectural leaves that cope with low light and little water.",
        "Stiff, sword-shaped leaves with yellow edges. It keeps its shape for years, needs water only every two to three weeks, and is happy in a dim corner or a bright bedroom.",
        {
            "light": "Low to bright indirect light",
            "water": "Every 2 to 3 weeks; let the soil dry out",
            "size": "About 40 cm tall",
            "pot": "6 inch nursery pot",
            "care_level": "Very easy",
            "pet_safe": False,
        },
    ),
    (
        "areca-palm",
        "Areca Palm",
        "Dypsis lutescens",
        "indoor",
        599,
        699,
        "Feathery palm fronds that make a room feel green and airy.",
        "Arching, golden-stemmed fronds that soften a living room corner or a covered balcony. It likes bright light and evenly moist soil, and grows steadily into a full clump.",
        {
            "light": "Bright indirect light",
            "water": "Twice a week in summer, weekly in winter",
            "size": "About 90 cm tall",
            "pot": "10 inch nursery pot",
            "care_level": "Easy",
            "pet_safe": True,
        },
    ),
    (
        "peace-lily",
        "Peace Lily",
        "Spathiphyllum wallisii",
        "indoor",
        399,
        None,
        "Dark leaves and white flowers that bloom even indoors.",
        "Deep green leaves with white flowers through much of the year. It droops when thirsty and perks up within hours of watering, so it tells you exactly when it needs you.",
        {
            "light": "Medium to bright indirect light",
            "water": "When the leaves begin to droop, or twice a week",
            "size": "About 40 cm tall",
            "pot": "6 inch nursery pot",
            "care_level": "Easy",
            "pet_safe": False,
        },
    ),
    (
        "zz-plant",
        "ZZ Plant",
        "Zamioculcas zamiifolia",
        "indoor",
        449,
        499,
        "Glossy, waxy leaves for offices and rooms with little sun.",
        "Thick stems of shiny leaves that store water, so it can go weeks without watering. Ideal for offices, reception desks and rooms with only artificial light.",
        {
            "light": "Low to bright indirect light",
            "water": "Every 2 to 3 weeks",
            "size": "About 45 cm tall",
            "pot": "6 inch nursery pot",
            "care_level": "Very easy",
            "pet_safe": False,
        },
    ),
    (
        "rubber-plant",
        "Rubber Plant",
        "Ficus elastica",
        "indoor",
        499,
        None,
        "Big, glossy burgundy-green leaves on a sturdy stem.",
        "Large leathery leaves that make a bold statement in a bright room. Wipe the leaves now and then to keep them shining. It grows tall slowly and can be pruned to stay bushy.",
        {
            "light": "Bright indirect light",
            "water": "Weekly; less in winter",
            "size": "About 60 cm tall",
            "pot": "8 inch nursery pot",
            "care_level": "Easy",
            "pet_safe": False,
        },
    ),
    (
        "hibiscus",
        "Hibiscus (Dasavala)",
        "Hibiscus rosa-sinensis",
        "flowering",
        299,
        349,
        "Large red flowers almost every day in a sunny spot.",
        "The classic Bangalore garden shrub with big red blooms that open fresh each morning. Grows well in a large pot on a sunny terrace or in the ground along a compound wall.",
        {
            "light": "Full sun, at least 5 hours",
            "water": "Daily in summer, every 2 days otherwise",
            "size": "About 45 cm tall",
            "pot": "8 inch nursery pot",
            "care_level": "Easy",
            "pet_safe": True,
        },
    ),
    (
        "jasmine",
        "Jasmine (Mallige)",
        "Jasminum sambac",
        "flowering",
        249,
        None,
        "Fragrant white flowers for pooja, hair and evening scent.",
        "Mysore mallige flowers heavily from March to October and fills a balcony with scent in the evening. Prune after each flush of flowers to keep it bushy and blooming.",
        {
            "light": "Full sun",
            "water": "Every 1 to 2 days in summer",
            "size": "About 40 cm tall",
            "pot": "8 inch nursery pot",
            "care_level": "Easy",
            "pet_safe": True,
        },
    ),
    (
        "bougainvillea",
        "Bougainvillea",
        "Bougainvillea glabra",
        "outdoor",
        349,
        399,
        "Sheets of pink colour for gates, compound walls and terraces.",
        "A tough, drought-hardy climber that covers a gate or wall in bright pink bracts for most of the year. It flowers best when slightly dry and in full sun, which makes it ideal for plots that are visited only now and then.",
        {
            "light": "Full sun",
            "water": "Twice a week; less once established",
            "size": "About 60 cm tall",
            "pot": "8 inch nursery pot",
            "care_level": "Very easy",
            "pet_safe": True,
        },
    ),
    (
        "curry-leaf",
        "Curry Leaf Plant",
        "Murraya koenigii",
        "herbs",
        199,
        None,
        "Fresh kariveppilai for your kitchen, from your own balcony.",
        "An aromatic shrub that gives fresh leaves all year. Pinch the tips to keep it bushy, give it plenty of sun, and it will keep the kitchen supplied for years.",
        {
            "light": "Full sun to partial shade",
            "water": "Every 2 days in summer",
            "size": "About 40 cm tall",
            "pot": "8 inch nursery pot",
            "care_level": "Easy",
            "pet_safe": True,
        },
    ),
    (
        "tulsi",
        "Tulsi (Holy Basil)",
        "Ocimum tenuiflorum",
        "herbs",
        149,
        None,
        "Krishna tulsi for the courtyard, pooja and kitchen.",
        "A sacred and medicinal herb with fragrant leaves. Keep it in a sunny spot, pinch off the flower spikes to keep it leafy, and water when the soil feels dry.",
        {
            "light": "Full sun",
            "water": "When the topsoil is dry, usually daily in summer",
            "size": "About 30 cm tall",
            "pot": "6 inch nursery pot",
            "care_level": "Easy",
            "pet_safe": True,
        },
    ),
    (
        "aloe-vera",
        "Aloe Vera",
        "Aloe barbadensis miller",
        "succulents",
        199,
        249,
        "A hardy succulent with soothing gel in every leaf.",
        "Plump, spiky leaves full of gel for minor burns and skin care. It needs very little water and lots of light, and makes new pups you can pot up for friends.",
        {
            "light": "Bright light to full sun",
            "water": "Every 2 weeks; never let it sit wet",
            "size": "About 25 cm tall",
            "pot": "6 inch nursery pot",
            "care_level": "Very easy",
            "pet_safe": False,
        },
    ),
]


def upgrade() -> None:
    products = op.create_table(
        "store_products",
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("botanical_name", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("care", sa.JSON(), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("mrp", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("image", sa.String(length=300), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_store_products_category"), "store_products", ["category"], unique=False)
    op.create_table(
        "store_orders",
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("bill_number", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payment_method", sa.String(length=10), nullable=False),
        sa.Column("payment_status", sa.String(length=10), nullable=False),
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("area", sa.String(length=120), nullable=False),
        sa.Column("pincode", sa.String(length=6), nullable=False),
        sa.Column("landmark", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("provider_order_id", sa.String(length=100), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=100), nullable=True),
        sa.Column("paid_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.String(length=300), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        *_stamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_number"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("number"),
    )
    op.create_index(op.f("ix_store_orders_provider_order_id"), "store_orders", ["provider_order_id"], unique=False)
    op.create_index(op.f("ix_store_orders_status"), "store_orders", ["status"], unique=False)
    op.create_table(
        "store_order_items",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=10, scale=2), nullable=False),
        *_stamps(),
        sa.ForeignKeyConstraint(["order_id"], ["store_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["store_products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_store_order_items_order_id"), "store_order_items", ["order_id"], unique=False)
    op.create_table(
        "store_counters",
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        *_stamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "year"),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        products,
        [
            {
                "id": uuid.uuid4(),
                "created_at": now,
                "updated_at": now,
                "slug": slug,
                "name": name,
                "botanical_name": botanical,
                "category": category,
                "summary": summary,
                "description": description,
                "care": care,
                "price": price,
                "mrp": mrp,
                "stock": None,
                "image": f"/store/{slug}.svg",
                "active": True,
                "sort_order": i * 10,
            }
            for i, (slug, name, botanical, category, price, mrp, summary, description, care) in enumerate(PLANTS)
        ],
    )


def downgrade() -> None:
    op.drop_table("store_counters")
    op.drop_index(op.f("ix_store_order_items_order_id"), table_name="store_order_items")
    op.drop_table("store_order_items")
    op.drop_index(op.f("ix_store_orders_status"), table_name="store_orders")
    op.drop_index(op.f("ix_store_orders_provider_order_id"), table_name="store_orders")
    op.drop_table("store_orders")
    op.drop_index(op.f("ix_store_products_category"), table_name="store_products")
    op.drop_table("store_products")
