-- Storage Policies for repo-data bucket
-- Run this in Supabase SQL Editor

-- Allow service role to upload files
CREATE POLICY "Allow service role uploads"
ON storage.objects
FOR INSERT
TO service_role
WITH CHECK (bucket_id = 'repo-data');

-- Allow service role to read files
CREATE POLICY "Allow service role reads"
ON storage.objects
FOR SELECT
TO service_role
USING (bucket_id = 'repo-data');

-- Allow service role to delete files
CREATE POLICY "Allow service role deletes"
ON storage.objects
FOR DELETE
TO service_role
USING (bucket_id = 'repo-data');

-- Allow service role to update files
CREATE POLICY "Allow service role updates"
ON storage.objects
FOR UPDATE
TO service_role
USING (bucket_id = 'repo-data');

