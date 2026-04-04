from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0005_community_rules_alter_community_created_by_and_more"),
        ("admin", "0003_logentry_add_action_flag_choices"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                # Remove rows that reference users no longer present in custom user table.
                """
                DELETE FROM django_admin_log l
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM api_user u
                    WHERE u.id = l.user_id
                );
                """,
                # Replace old FK (auth_user) with FK to custom user table.
                """
                ALTER TABLE django_admin_log
                DROP CONSTRAINT IF EXISTS django_admin_log_user_id_c564eba6_fk_auth_user_id;
                """,
                """
                ALTER TABLE django_admin_log
                DROP CONSTRAINT IF EXISTS django_admin_log_user_id_c564eba6_fk_api_user_id;
                """,
                """
                ALTER TABLE django_admin_log
                ADD CONSTRAINT django_admin_log_user_id_c564eba6_fk_api_user_id
                FOREIGN KEY (user_id) REFERENCES api_user(id)
                DEFERRABLE INITIALLY DEFERRED;
                """,
            ],
            reverse_sql=[
                """
                ALTER TABLE django_admin_log
                DROP CONSTRAINT IF EXISTS django_admin_log_user_id_c564eba6_fk_api_user_id;
                """,
                """
                ALTER TABLE django_admin_log
                ADD CONSTRAINT django_admin_log_user_id_c564eba6_fk_auth_user_id
                FOREIGN KEY (user_id) REFERENCES auth_user(id)
                DEFERRABLE INITIALLY DEFERRED;
                """,
            ],
        )
    ]
