"""marketing blog: posts and their pictures

Revision ID: b4d81e6f2a17
Revises: 7c2e4f9a1b3d
Create Date: 2026-10-26 15:00:00

The four guides that were written into the website's code move here, so they can be edited
from the office's Blog page. Prices in them are {{…}} tokens that the website fills in from
its service price list, so a price change still updates the guides.
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.models.base


# revision identifiers, used by Alembic.
revision: str = "b4d81e6f2a17"
down_revision: Union[str, Sequence[str], None] = "7c2e4f9a1b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _stamps():
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.models.base.UTCDateTime(timezone=True), nullable=False),
    ]


GUIDES = [
    dict(
        slug="plot-cleaning-cost-bangalore",
        title="How much does plot cleaning cost in Bangalore?",
        excerpt="Plot cleaning prices in Bangalore per sq ft, what changes the price, and when an annual plan works out cheaper than paying per visit.",
        cover_image="/site/plot-cleaning-bangalore.jpg",
        cover_alt="A vacant plot in Bangalore being cleared of weeds",
        category="costs",
        tags=["Plot cleaning", "Prices", "AMC"],
        services=["plot-cleaning", "property-inspection"],
        seo_title="Plot Cleaning Cost in Bangalore (Per Sq Ft Prices)",
        featured=True,
        body="""Plot cleaning in Bangalore is usually priced by the size of the plot. The price also depends on how overgrown the plot is, whether there is construction waste to remove, and whether a vehicle can reach it.

At GreenPlot, a basic cleaning visit costs {{rate:plot-cleaning}} per sq ft, with a minimum of {{minimum:plot-cleaning}} a visit.

## Typical prices by plot size

These are basic estimates for one cleaning visit on level ground that a vehicle can reach.

- 30 x 40 (1,200 sq ft): {{estimate:plot-cleaning:1200}}
- 30 x 50 (1,500 sq ft): {{estimate:plot-cleaning:1500}}
- 40 x 60 (2,400 sq ft): {{estimate:plot-cleaning:2400}}
- 50 x 80 (4,000 sq ft): {{estimate:plot-cleaning:4000}}

## What makes it cost more

{{terrain-note}}

- Waist-high grass and shrubs that need cutting before clearing
- Dumped construction waste that has to be carried away
- Slopes, rocky ground or no road access
- Large trees that need trimming

## Per visit or an annual plan?

If you need the plot cleaned more than three or four times a year, an annual maintenance contract (AMC) is cheaper. Our {{plan:plot-cleaning:1}} plan includes {{plan-summary:plot-cleaning:1}} from {{plan-rate:plot-cleaning:1}} per sq ft a year, and every plan comes with a photo report after each visit.

Most vacant plots in Bangalore need cleaning every three months, and every one to two months during and after the monsoon.
""",
    ),
    dict(
        slug="nri-guide-bangalore-plot",
        title="NRI guide: looking after your Bangalore plot from abroad",
        excerpt="How owners living abroad keep their Bangalore plot clean, protected and documented without travelling, and what to ask a maintenance company.",
        cover_image="/site/property-inspection-bangalore.jpg",
        cover_alt="A GreenPlot inspector photographing a plot boundary in Bangalore",
        category="nri",
        tags=["NRI", "Property Watch", "Plot cleaning"],
        services=["property-inspection", "plot-cleaning", "fencing-gates"],
        seo_title=None,
        featured=False,
        body="""A vacant plot that nobody visits slowly becomes a problem. Weeds grow, people dump waste, boundary stones go missing and, in the worst cases, someone starts using the land. If you live abroad, the answer is a simple routine and someone you can trust to follow it.

## A routine that works

This is what we suggest to owners who cannot visit.

- An inspection visit at least every three months, with photos of every boundary
- Cleaning before and after the monsoon, and more often if the plot is next to open land
- A fence or at least clear boundary markers, so the plot's edges are never in doubt
- All photos and reports stored in one place, so you have a record if you sell or build

## What to ask a maintenance company

Before you pay anyone, ask how you will know each visit really happened.

- Do you send before and after photos from every visit, with the time?
- Who checks the work before it is marked done?
- Can I see all past visits in one place?
- How do I pay from abroad, and do I get a receipt?

## How GreenPlot does it

Our Property Watch inspection starts at {{rate:property-inspection}} per sq ft a visit. Every visit is photographed, checked by a supervisor and sent to you on WhatsApp or email, and you pay online.
""",
    ),
    dict(
        slug="protect-vacant-plot-encroachment",
        title="How to protect a vacant plot from encroachment",
        excerpt="Practical steps Bangalore plot owners can take to keep their land secure: boundaries, fencing, regular visits and keeping your records in order.",
        cover_image="/site/plot-fencing-gates-bangalore.jpg",
        cover_alt="A fenced plot in Bangalore with a locked gate",
        category="protection",
        tags=["Encroachment", "Fencing", "Property Watch"],
        services=["fencing-gates", "property-inspection"],
        seo_title=None,
        featured=False,
        body="""Encroachment usually starts small: a pile of building material, a temporary shed, a path across the corner of the plot. It is much easier to stop early, and the best protection is a plot that clearly looks owned and looked after.

## Five steps that help

- Keep the boundary stones visible and photograph them on every visit
- Put up a fence or compound wall, with a gate that locks
- Fix a board with the owner's name or a contact number
- Visit, or have someone visit, at least every three months
- Keep your sale deed, khata and tax receipts safe and up to date

## If something has already happened

Photograph it straight away, note the date, and speak to a property lawyer before you act. Dated photos from regular visits are useful evidence that the plot was clear before.
""",
    ),
    dict(
        slug="pre-monsoon-plot-checklist",
        title="Pre-monsoon checklist for Bangalore plot owners",
        excerpt="What to do to your plot before the Bangalore monsoon: clearing, drainage, trees, fencing and the checks that save money later.",
        cover_image="/site/garden-maintenance-bangalore.jpg",
        cover_alt="Gardeners trimming trees on a Bangalore plot before the rains",
        category="seasonal",
        tags=["Monsoon", "Plot cleaning", "Gardening"],
        services=["plot-cleaning", "garden-landscape", "fencing-gates"],
        seo_title=None,
        featured=False,
        body="""Bangalore's rains make weeds grow fast and expose any weak fence or blocked drain. A little work before the monsoon, usually in April or May, saves a much bigger cleaning bill later.

## The checklist

- Clear weeds, dry grass and debris so water can drain
- Make sure the plot does not block the drain along the road
- Trim trees and branches that hang over neighbours or power lines
- Check fence posts and gates, and repair anything loose before the wind and rain
- Book a cleaning visit for just after the monsoon

## Plots with gardens

If your plot has a lawn or trees, a garden plan keeps it under control through the rains. Our {{plan:garden-landscape:3}} garden plan includes tree pruning before the monsoon.
""",
    ),
]


def upgrade() -> None:
    op.create_table(
        "blog_posts",
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("excerpt", sa.String(length=320), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("cover_image", sa.String(length=300), nullable=True),
        sa.Column("cover_alt", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("seo_title", sa.String(length=70), nullable=True),
        sa.Column("seo_description", sa.String(length=170), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("published_at", app.models.base.UTCDateTime(timezone=True), nullable=True),
        sa.Column("featured", sa.Boolean(), nullable=False),
        sa.Column("author_name", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_blog_posts_category"), "blog_posts", ["category"], unique=False)
    op.create_index(op.f("ix_blog_posts_status"), "blog_posts", ["status"], unique=False)
    op.create_index(op.f("ix_blog_posts_published_at"), "blog_posts", ["published_at"], unique=False)
    op.create_table(
        "blog_images",
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )

    posts = sa.table(
        "blog_posts",
        *[sa.column(c) for c in ("id", "created_at", "updated_at", "slug", "title", "excerpt", "body", "cover_image", "cover_alt", "category", "status", "published_at", "featured", "author_name", "seo_title", "seo_description")],
        sa.column("tags", sa.JSON()),
        sa.column("services", sa.JSON()),
    )
    # The date the guides first went live on the website.
    published = datetime(2026, 10, 26, 4, 30, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        posts,
        [
            {
                "id": uuid.uuid4(),
                "created_at": now,
                "updated_at": now,
                "status": "published",
                "published_at": published,
                "author_name": "GreenPlot team",
                "seo_description": None,
                **g,
            }
            for g in GUIDES
        ],
    )


def downgrade() -> None:
    op.drop_table("blog_images")
    op.drop_index(op.f("ix_blog_posts_published_at"), table_name="blog_posts")
    op.drop_index(op.f("ix_blog_posts_status"), table_name="blog_posts")
    op.drop_index(op.f("ix_blog_posts_category"), table_name="blog_posts")
    op.drop_table("blog_posts")
