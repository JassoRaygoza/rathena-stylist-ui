-- Stylist durable accessory delivery. Run on the character database.
-- Back up these tables first, then stop map/char while migrating/deploying.
-- Adjust table names if they are customized in inter_athena.conf.
-- ALTER TABLE commits implicitly: this migration is not one atomic transaction.
ALTER TABLE `char` ENGINE=InnoDB;
ALTER TABLE `inventory` ENGINE=InnoDB;
ALTER TABLE `mail` ENGINE=InnoDB;
ALTER TABLE `mail_attachments` ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `stylist_purchase` (
  `operation_id` char(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `account_id` int unsigned NOT NULL,
  `char_id` int unsigned NOT NULL,
  `request_hash` binary(32) NOT NULL,
  `result` tinyint unsigned NOT NULL,
  `mail_id` int unsigned NOT NULL DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`operation_id`),
  KEY `character_history` (`char_id`,`created_at`)
) ENGINE=InnoDB;

-- Preserve this journal when rolling back code or restoring a backup.
-- Do not purge IDs while any map server may still retry an outstanding request.
-- Reverting code requires disabling stylist_accessory_mail and resolving pending
-- purchases first. Keeping these tables on InnoDB is compatible with old code.
