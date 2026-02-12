import express from 'express';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import ytDlp from 'yt-dlp-exec';
import { createClient } from '@supabase/supabase-js';
import 'dotenv/config';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3001;

// Middleware
app.use(cors());
app.use(express.json());

// Supabase config
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;

if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
    console.error('Missing Supabase configuration. Please check your .env file.');
    process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

// Ensure temp directory exists
const TEMP_DIR = path.join(__dirname, 'temp_downloads');
if (!fs.existsSync(TEMP_DIR)) {
    fs.mkdirSync(TEMP_DIR, { recursive: true });
}

// Download tweet video endpoint
app.post('/api/download-tweet', async (req, res) => {
    const { url, user_id, caption } = req.body;

    if (!url) {
        return res.status(400).json({ error: 'URL is required' });
    }

    if (!user_id) {
        return res.status(400).json({ error: 'User ID is required' });
    }

    console.log(`[Download] Starting download for: ${url}`);

    const filename = `${Date.now()}_tweet_video.mp4`;
    const outputPath = path.join(TEMP_DIR, filename);

    try {
        // Download video using yt-dlp
        await ytDlp(url, {
            output: outputPath,
            format: 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            noCheckCertificates: true,
            noPlaylist: true,
        });

        console.log(`[Download] Video downloaded to: ${outputPath}`);

        // Check if file exists
        if (!fs.existsSync(outputPath)) {
            throw new Error('Downloaded file not found');
        }

        // Read file and upload to Supabase Storage
        const fileBuffer = fs.readFileSync(outputPath);
        const { error: uploadError } = await supabase.storage
            .from('temp_video_queue')
            .upload(filename, fileBuffer, {
                contentType: 'video/mp4',
                upsert: false
            });

        if (uploadError) {
            throw new Error(`Storage upload failed: ${uploadError.message}`);
        }

        console.log(`[Download] Uploaded to Supabase storage: ${filename}`);

        // Insert record into video_queue table
        const { data: queueData, error: queueError } = await supabase
            .from('video_queue')
            .insert({
                user_id,
                tweet_url: url,
                video_filename: filename,
                caption: caption || '',
                status: 'pending'
            })
            .select()
            .single();

        if (queueError) {
            console.error('[Download] Queue insert error:', queueError);
            // Still return success since video is uploaded
        }

        // Clean up temp file
        fs.unlinkSync(outputPath);
        console.log(`[Download] Cleaned up temp file`);

        res.json({
            success: true,
            video_filename: filename,
            queue_id: queueData?.id,
            message: 'Video downloaded and queued successfully'
        });

    } catch (error) {
        console.error('[Download] Error:', error);

        // Clean up temp file if it exists
        if (fs.existsSync(outputPath)) {
            fs.unlinkSync(outputPath);
        }

        res.status(500).json({
            error: error.message || 'Failed to download video'
        });
    }
});

// Get all queued videos for a user
app.get('/api/queue/:user_id', async (req, res) => {
    const { user_id } = req.params;

    try {
        const { data, error } = await supabase
            .from('video_queue')
            .select('*')
            .eq('user_id', user_id)
            .eq('status', 'pending')
            .order('created_at', { ascending: false });

        if (error) {
            throw error;
        }

        res.json({ videos: data || [] });
    } catch (error) {
        console.error('[Queue] Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Delete a video from queue
app.delete('/api/queue/:id', async (req, res) => {
    const { id } = req.params;

    try {
        // Get the video record first
        const { data: video, error: fetchError } = await supabase
            .from('video_queue')
            .select('video_filename')
            .eq('id', id)
            .single();

        if (fetchError || !video) {
            return res.status(404).json({ error: 'Video not found' });
        }

        // Delete from storage
        const { error: storageError } = await supabase.storage
            .from('temp_video_queue')
            .remove([video.video_filename]);

        if (storageError) {
            console.error('[Delete] Storage delete error:', storageError);
        }

        // Delete from database
        const { error: deleteError } = await supabase
            .from('video_queue')
            .delete()
            .eq('id', id);

        if (deleteError) {
            throw deleteError;
        }

        res.json({ success: true, message: 'Video deleted from queue' });
    } catch (error) {
        console.error('[Delete] Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Mark video as uploaded and remove from queue
app.post('/api/queue/:id/complete', async (req, res) => {
    const { id } = req.params;

    try {
        // Get the video record
        const { data: video, error: fetchError } = await supabase
            .from('video_queue')
            .select('video_filename')
            .eq('id', id)
            .single();

        if (fetchError || !video) {
            return res.status(404).json({ error: 'Video not found' });
        }

        // Delete from storage (edge function should already do this, but just in case)
        await supabase.storage
            .from('temp_video_queue')
            .remove([video.video_filename]);

        // Delete from queue table
        await supabase
            .from('video_queue')
            .delete()
            .eq('id', id);

        res.json({ success: true, message: 'Video removed from queue' });
    } catch (error) {
        console.error('[Complete] Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Health check
app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
    console.log(`🚀 Tweet Downloader Server running on http://localhost:${PORT}`);
    console.log(`   - POST /api/download-tweet - Download a tweet video`);
    console.log(`   - GET  /api/queue/:user_id - Get queued videos`);
    console.log(`   - DELETE /api/queue/:id - Delete from queue`);
    console.log(`   - POST /api/queue/:id/complete - Mark as uploaded`);
});
