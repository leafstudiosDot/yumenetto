from django.db import migrations


THREAD_COLUMNS_SQL = """
    id,
    community_id,
    author_id,
    title,
    description,
    image,
    adult_content,
    created_at,
    updated_at,
    last_activity,
    status,
    removal_reason,
    is_locked,
    is_deleted
"""

REPLY_COLUMNS_SQL = """
    id,
    thread_id,
    author_id,
    content,
    created_at,
    updated_at,
    status,
    removal_reason,
    is_deleted,
    is_edited
"""

EMPTY_THREAD_SQL = """
SELECT
    NULL::bigint AS id,
    NULL::bigint AS community_id,
    NULL::bigint AS author_id,
    ''::varchar(200) AS title,
    ''::text AS description,
    NULL::varchar(255) AS image,
    FALSE::boolean AS adult_content,
    NOW()::timestamptz AS created_at,
    NOW()::timestamptz AS updated_at,
    NOW()::timestamptz AS last_activity,
    'public'::varchar(32) AS status,
    ''::text AS removal_reason,
    FALSE::boolean AS is_locked,
    FALSE::boolean AS is_deleted
WHERE FALSE
"""

EMPTY_REPLY_SQL = """
SELECT
    NULL::bigint AS id,
    NULL::bigint AS thread_id,
    NULL::bigint AS author_id,
    ''::text AS content,
    NOW()::timestamptz AS created_at,
    NOW()::timestamptz AS updated_at,
    'public'::varchar(32) AS status,
    ''::text AS removal_reason,
    FALSE::boolean AS is_deleted,
    FALSE::boolean AS is_edited
WHERE FALSE
"""


def _table_exists(cursor, relation_name):
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [relation_name])
    return bool(cursor.fetchone()[0])


def create_admin_compat_views(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'postgresql':
        return

    Community = apps.get_model('api', 'Community')
    qn = connection.ops.quote_name

    thread_selects = []
    reply_selects = []

    with connection.cursor() as cursor:
        communities = Community.objects.exclude(schema_name__isnull=True).exclude(schema_name='')

        for community in communities.iterator():
            thread_relation = f"{community.schema_name}.threads"
            reply_relation = f"{community.schema_name}.replies"

            if _table_exists(cursor, thread_relation):
                thread_table = f"{qn(community.schema_name)}.{qn('threads')}"
                thread_selects.append(f"SELECT {THREAD_COLUMNS_SQL} FROM {thread_table}")

            if _table_exists(cursor, reply_relation):
                reply_table = f"{qn(community.schema_name)}.{qn('replies')}"
                reply_selects.append(f"SELECT {REPLY_COLUMNS_SQL} FROM {reply_table}")

        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_reply')}")
        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_thread')}")

        thread_sql = " UNION ALL ".join(thread_selects) if thread_selects else EMPTY_THREAD_SQL
        reply_sql = " UNION ALL ".join(reply_selects) if reply_selects else EMPTY_REPLY_SQL

        cursor.execute(f"CREATE VIEW {qn('api_thread')} AS {thread_sql}")
        cursor.execute(f"CREATE VIEW {qn('api_reply')} AS {reply_sql}")


def drop_admin_compat_views(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'postgresql':
        return

    qn = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_reply')}")
        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_thread')}")


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_move_thread_reply_to_community_schemas'),
    ]

    operations = [
        migrations.RunPython(create_admin_compat_views, drop_admin_compat_views),
    ]
