-- One-off cleanup for rows created by the bare-drive bug ("D:file" instead of "D:\file").
-- Back up the database first. Preview with: SELECT COUNT(*) FROM files WHERE path GLOB '[A-Za-z]:[^\]*';
DELETE FROM files WHERE path GLOB '[A-Za-z]:[^\]*';
