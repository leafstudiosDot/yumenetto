from django.db import migrations


THREAD_COLUMNS_SQL = """
    ((community_id::bigint << 32) + id) AS id,
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
    ((t.community_id::bigint << 32) + r.id) AS id,
    ((t.community_id::bigint << 32) + r.thread_id) AS thread_id,
    r.author_id,
    r.content,
    r.created_at,
    r.updated_at,
    r.status,
    r.removal_reason,
    r.is_deleted,
    r.is_edited
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


def _create_views(connection, communities):
    qn = connection.ops.quote_name
    thread_selects = []
    reply_selects = []

    with connection.cursor() as cursor:
        for community in communities:
            thread_relation = f"{community.schema_name}.threads"
            reply_relation = f"{community.schema_name}.replies"

            if _table_exists(cursor, thread_relation):
                thread_table = f"{qn(community.schema_name)}.{qn('threads')}"
                thread_selects.append(f"SELECT {THREAD_COLUMNS_SQL} FROM {thread_table}")

            if _table_exists(cursor, reply_relation):
                reply_table = f"{qn(community.schema_name)}.{qn('replies')}"
                thread_table = f"{qn(community.schema_name)}.{qn('threads')}"
                reply_selects.append(
                    f"SELECT {REPLY_COLUMNS_SQL} FROM {reply_table} r INNER JOIN {thread_table} t ON t.id = r.thread_id"
                )

        cursor.execute('DROP TRIGGER IF EXISTS api_reply_view_iud ON api_reply')
        cursor.execute('DROP TRIGGER IF EXISTS api_thread_view_iud ON api_thread')
        cursor.execute('DROP FUNCTION IF EXISTS api_reply_view_iud()')
        cursor.execute('DROP FUNCTION IF EXISTS api_thread_view_iud()')

        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_reply')}")
        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_thread')}")

        thread_sql = " UNION ALL ".join(thread_selects) if thread_selects else EMPTY_THREAD_SQL
        reply_sql = " UNION ALL ".join(reply_selects) if reply_selects else EMPTY_REPLY_SQL

        cursor.execute(f"CREATE VIEW {qn('api_thread')} AS {thread_sql}")
        cursor.execute(f"CREATE VIEW {qn('api_reply')} AS {reply_sql}")

        cursor.execute(
            """
            CREATE FUNCTION api_thread_view_iud()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                schema_name text;
                local_id bigint;
                mask constant bigint := 4294967295;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.community_id IS NULL THEN
                        RAISE EXCEPTION 'community_id is required';
                    END IF;

                    SELECT c.schema_name INTO schema_name
                    FROM api_community c
                    WHERE c.id = NEW.community_id;

                    IF schema_name IS NULL OR schema_name = '' THEN
                        RAISE EXCEPTION 'community % has no schema_name', NEW.community_id;
                    END IF;

                    EXECUTE format(
                        'INSERT INTO %I.threads (community_id, author_id, title, description, image, adult_content, created_at, updated_at, last_activity, status, removal_reason, is_locked, is_deleted) '
                        || 'VALUES ($1,$2,$3,$4,$5,$6,COALESCE($7,NOW()),COALESCE($8,NOW()),COALESCE($9,NOW()),$10,$11,$12,$13) RETURNING id, created_at, updated_at, last_activity',
                        schema_name
                    )
                    INTO local_id, NEW.created_at, NEW.updated_at, NEW.last_activity
                    USING NEW.community_id, NEW.author_id, NEW.title, NEW.description, NEW.image, NEW.adult_content,
                          NEW.created_at, NEW.updated_at, NEW.last_activity, NEW.status, NEW.removal_reason,
                          NEW.is_locked, NEW.is_deleted;

                    NEW.id := ((NEW.community_id::bigint << 32) + local_id);
                    RETURN NEW;
                ELSIF TG_OP = 'UPDATE' THEN
                    IF NEW.community_id <> OLD.community_id THEN
                        RAISE EXCEPTION 'Changing thread community is not supported in admin view';
                    END IF;

                    SELECT c.schema_name INTO schema_name
                    FROM api_community c
                    WHERE c.id = OLD.community_id;

                    local_id := (OLD.id::bigint & mask);

                    EXECUTE format(
                        'UPDATE %I.threads SET author_id=$1, title=$2, description=$3, image=$4, adult_content=$5, updated_at=COALESCE($6,NOW()), last_activity=COALESCE($7,NOW()), status=$8, removal_reason=$9, is_locked=$10, is_deleted=$11 WHERE id=$12',
                        schema_name
                    )
                    USING NEW.author_id, NEW.title, NEW.description, NEW.image, NEW.adult_content,
                          NEW.updated_at, NEW.last_activity, NEW.status, NEW.removal_reason,
                          NEW.is_locked, NEW.is_deleted, local_id;

                    NEW.id := OLD.id;
                    RETURN NEW;
                ELSE
                    SELECT c.schema_name INTO schema_name
                    FROM api_community c
                    WHERE c.id = OLD.community_id;

                    local_id := (OLD.id::bigint & mask);

                    EXECUTE format('DELETE FROM %I.threads WHERE id = $1', schema_name)
                    USING local_id;

                    RETURN OLD;
                END IF;
            END;
            $$
            """
        )

        cursor.execute(
            """
            CREATE FUNCTION api_reply_view_iud()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                schema_name text;
                local_id bigint;
                local_thread_id bigint;
                old_community_id bigint;
                new_community_id bigint;
                mask constant bigint := 4294967295;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.thread_id IS NULL THEN
                        RAISE EXCEPTION 'thread_id is required';
                    END IF;

                    new_community_id := (NEW.thread_id::bigint >> 32);
                    local_thread_id := (NEW.thread_id::bigint & mask);

                    SELECT c.schema_name INTO schema_name
                    FROM api_community c
                    WHERE c.id = new_community_id;

                    IF schema_name IS NULL OR schema_name = '' THEN
                        RAISE EXCEPTION 'community % has no schema_name', new_community_id;
                    END IF;

                    EXECUTE format(
                        'INSERT INTO %I.replies (thread_id, author_id, content, created_at, updated_at, status, removal_reason, is_deleted, is_edited) '
                        || 'VALUES ($1,$2,$3,COALESCE($4,NOW()),COALESCE($5,NOW()),$6,$7,$8,$9) RETURNING id, created_at, updated_at',
                        schema_name
                    )
                    INTO local_id, NEW.created_at, NEW.updated_at
                    USING local_thread_id, NEW.author_id, NEW.content, NEW.created_at, NEW.updated_at,
                          NEW.status, NEW.removal_reason, NEW.is_deleted, NEW.is_edited;

                    NEW.id := ((new_community_id << 32) + local_id);
                    RETURN NEW;
                ELSIF TG_OP = 'UPDATE' THEN
                    old_community_id := (OLD.id::bigint >> 32);
                    new_community_id := (NEW.thread_id::bigint >> 32);

                    IF old_community_id <> new_community_id THEN
                        RAISE EXCEPTION 'Moving replies across communities is not supported in admin view';
                    END IF;

                    local_id := (OLD.id::bigint & mask);
                    local_thread_id := (NEW.thread_id::bigint & mask);

                    SELECT c.schema_name INTO schema_name
                    FROM api_community c
                    WHERE c.id = old_community_id;

                    EXECUTE format(
                        'UPDATE %I.replies SET thread_id=$1, author_id=$2, content=$3, updated_at=COALESCE($4,NOW()), status=$5, removal_reason=$6, is_deleted=$7, is_edited=$8 WHERE id=$9',
                        schema_name
                    )
                    USING local_thread_id, NEW.author_id, NEW.content, NEW.updated_at, NEW.status,
                          NEW.removal_reason, NEW.is_deleted, NEW.is_edited, local_id;

                    NEW.id := OLD.id;
                    RETURN NEW;
                ELSE
                    old_community_id := (OLD.id::bigint >> 32);
                    local_id := (OLD.id::bigint & mask);

                    SELECT c.schema_name INTO schema_name
                    FROM api_community c
                    WHERE c.id = old_community_id;

                    EXECUTE format('DELETE FROM %I.replies WHERE id = $1', schema_name)
                    USING local_id;

                    RETURN OLD;
                END IF;
            END;
            $$
            """
        )

        cursor.execute(
            'CREATE TRIGGER api_thread_view_iud INSTEAD OF INSERT OR UPDATE OR DELETE ON api_thread FOR EACH ROW EXECUTE FUNCTION api_thread_view_iud()'
        )
        cursor.execute(
            'CREATE TRIGGER api_reply_view_iud INSTEAD OF INSERT OR UPDATE OR DELETE ON api_reply FOR EACH ROW EXECUTE FUNCTION api_reply_view_iud()'
        )


def create_writable_admin_compat_views(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'postgresql':
        return

    Community = apps.get_model('api', 'Community')
    communities = Community.objects.exclude(schema_name__isnull=True).exclude(schema_name='').order_by('name')
    _create_views(connection, communities.iterator())


def revert_to_readonly_compat_views(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'postgresql':
        return

    Community = apps.get_model('api', 'Community')
    qn = connection.ops.quote_name

    with connection.cursor() as cursor:
        cursor.execute('DROP TRIGGER IF EXISTS api_reply_view_iud ON api_reply')
        cursor.execute('DROP TRIGGER IF EXISTS api_thread_view_iud ON api_thread')
        cursor.execute('DROP FUNCTION IF EXISTS api_reply_view_iud()')
        cursor.execute('DROP FUNCTION IF EXISTS api_thread_view_iud()')

    thread_selects = []
    reply_selects = []
    with connection.cursor() as cursor:
        for community in Community.objects.exclude(schema_name__isnull=True).exclude(schema_name='').order_by('name').iterator():
            thread_relation = f"{community.schema_name}.threads"
            reply_relation = f"{community.schema_name}.replies"

            if _table_exists(cursor, thread_relation):
                thread_table = f"{qn(community.schema_name)}.{qn('threads')}"
                thread_selects.append(
                    f"SELECT id, community_id, author_id, title, description, image, adult_content, created_at, updated_at, last_activity, status, removal_reason, is_locked, is_deleted FROM {thread_table}"
                )

            if _table_exists(cursor, reply_relation):
                reply_table = f"{qn(community.schema_name)}.{qn('replies')}"
                reply_selects.append(
                    f"SELECT id, thread_id, author_id, content, created_at, updated_at, status, removal_reason, is_deleted, is_edited FROM {reply_table}"
                )

        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_reply')}")
        cursor.execute(f"DROP VIEW IF EXISTS {qn('api_thread')}")

        thread_sql = " UNION ALL ".join(thread_selects) if thread_selects else EMPTY_THREAD_SQL
        reply_sql = " UNION ALL ".join(reply_selects) if reply_selects else EMPTY_REPLY_SQL

        cursor.execute(f"CREATE VIEW {qn('api_thread')} AS {thread_sql}")
        cursor.execute(f"CREATE VIEW {qn('api_reply')} AS {reply_sql}")


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_create_admin_compat_views'),
    ]

    operations = [
        migrations.RunPython(create_writable_admin_compat_views, revert_to_readonly_compat_views),
    ]
