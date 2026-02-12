// Follow this Deno/Oak style guide for Supabase Edge Functions
import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

interface RequestBody {
    video_filename: string
    caption: string
    user_id: string
}

interface Credentials {
    youtube?: {
        clientId: string
        clientSecret: string
        refreshToken: string
    }
    instagram?: {
        accessToken: string
        accountId: string
    }
}

// Refresh YouTube access token using refresh token
async function getYouTubeAccessToken(clientId: string, clientSecret: string, refreshToken: string): Promise<string> {
    const response = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            client_id: clientId,
            client_secret: clientSecret,
            refresh_token: refreshToken,
            grant_type: 'refresh_token',
        }),
    })

    const data = await response.json()
    if (!data.access_token) {
        throw new Error(`Failed to refresh YouTube token: ${JSON.stringify(data)}`)
    }
    return data.access_token
}

// Upload video to YouTube Shorts
async function uploadToYouTube(
    accessToken: string,
    videoUrl: string,
    caption: string
): Promise<{ success: boolean; videoId?: string; error?: string }> {
    try {
        // Fetch the video binary from Supabase
        const videoResponse = await fetch(videoUrl)
        if (!videoResponse.ok) {
            throw new Error('Failed to fetch video from storage')
        }
        const videoBlob = await videoResponse.blob()

        // Create video metadata
        const metadata = {
            snippet: {
                title: caption.substring(0, 100), // YouTube title max 100 chars
                description: caption,
                categoryId: '22', // People & Blogs
                tags: ['Shorts'],
            },
            status: {
                privacyStatus: 'public',
                selfDeclaredMadeForKids: false,
            },
        }

        // Step 1: Initialize resumable upload
        const initResponse = await fetch(
            'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
            {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    'Content-Type': 'application/json',
                    'X-Upload-Content-Type': 'video/mp4',
                    'X-Upload-Content-Length': videoBlob.size.toString(),
                },
                body: JSON.stringify(metadata),
            }
        )

        if (!initResponse.ok) {
            const error = await initResponse.text()
            throw new Error(`YouTube init failed: ${error}`)
        }

        const uploadUrl = initResponse.headers.get('Location')
        if (!uploadUrl) {
            throw new Error('No upload URL returned from YouTube')
        }

        // Step 2: Upload the video binary
        const uploadResponse = await fetch(uploadUrl, {
            method: 'PUT',
            headers: {
                'Content-Type': 'video/mp4',
                'Content-Length': videoBlob.size.toString(),
            },
            body: videoBlob,
        })

        if (!uploadResponse.ok) {
            const error = await uploadResponse.text()
            throw new Error(`YouTube upload failed: ${error}`)
        }

        const result = await uploadResponse.json()
        return { success: true, videoId: result.id }
    } catch (error: unknown) {
        console.error('YouTube upload error:', error)
        const errorMessage = error instanceof Error ? error.message : String(error)
        return { success: false, error: errorMessage }
    }
}

// Upload video to Instagram Reels
async function uploadToInstagram(
    accessToken: string,
    accountId: string,
    videoUrl: string,
    caption: string
): Promise<{ success: boolean; mediaId?: string; error?: string }> {
    try {
        // Step 1: Create media container
        const containerResponse = await fetch(
            `https://graph.facebook.com/v18.0/${accountId}/media`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    media_type: 'REELS',
                    video_url: videoUrl,
                    caption: caption,
                    access_token: accessToken,
                }),
            }
        )

        const containerData = await containerResponse.json()
        if (containerData.error) {
            throw new Error(`Instagram container error: ${containerData.error.message}`)
        }

        const creationId = containerData.id
        console.log(`Instagram container created: ${creationId}`)

        // Step 2: Poll for container status (max 60 seconds)
        const maxWaitTime = 60000
        const pollInterval = 5000
        let elapsed = 0
        let status = 'IN_PROGRESS'

        while (status !== 'FINISHED' && elapsed < maxWaitTime) {
            await new Promise(resolve => setTimeout(resolve, pollInterval))
            elapsed += pollInterval

            const statusResponse = await fetch(
                `https://graph.facebook.com/v18.0/${creationId}?fields=status_code&access_token=${accessToken}`
            )
            const statusData = await statusResponse.json()
            status = statusData.status_code

            console.log(`Instagram container status: ${status} (${elapsed / 1000}s)`)

            if (status === 'ERROR') {
                throw new Error('Instagram video processing failed')
            }
        }

        if (status !== 'FINISHED') {
            throw new Error('Instagram processing timeout (60s)')
        }

        // Step 3: Publish the container
        const publishResponse = await fetch(
            `https://graph.facebook.com/v18.0/${accountId}/media_publish`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    creation_id: creationId,
                    access_token: accessToken,
                }),
            }
        )

        const publishData = await publishResponse.json()
        if (publishData.error) {
            throw new Error(`Instagram publish error: ${publishData.error.message}`)
        }

        return { success: true, mediaId: publishData.id }
    } catch (error: unknown) {
        console.error('Instagram upload error:', error)
        const errorMessage = error instanceof Error ? error.message : String(error)
        return { success: false, error: errorMessage }
    }
}

// Hardcoded credentials
const SUPABASE_URL = Deno.env.get('SUPABASE_URL') || ''
const SUPABASE_SERVICE_KEY = Deno.env.get('SUPABASE_SERVICE_KEY') || ''

const YOUTUBE_CLIENT_ID = Deno.env.get('YOUTUBE_CLIENT_ID') || ''
const YOUTUBE_CLIENT_SECRET = Deno.env.get('YOUTUBE_CLIENT_SECRET') || ''
const YOUTUBE_REFRESH_TOKEN = Deno.env.get('YOUTUBE_REFRESH_TOKEN') || ''

const INSTAGRAM_ACCESS_TOKEN = Deno.env.get('INSTAGRAM_ACCESS_TOKEN') || ''
const INSTAGRAM_ACCOUNT_ID = Deno.env.get('INSTAGRAM_ACCOUNT_ID') || ''

serve(async (req) => {
    // Handle CORS preflight
    if (req.method === 'OPTIONS') {
        return new Response(null, { headers: corsHeaders })
    }

    try {
        if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
            throw new Error('Missing Supabase configuration')
        }

        const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY)

        // Parse request body
        const { video_filename, caption, user_id }: RequestBody = await req.json()

        if (!video_filename || !caption || !user_id) {
            return new Response(
                JSON.stringify({ error: 'Missing required fields' }),
                { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
            )
        }

        console.log(`Processing video: ${video_filename} for user: ${user_id}`)

        // Generate signed URL for the video (valid for 10 minutes)
        const { data: signedUrlData, error: signedUrlError } = await supabase.storage
            .from('temp_video_queue')
            .createSignedUrl(video_filename, 600) // 600 seconds = 10 minutes

        if (signedUrlError || !signedUrlData?.signedUrl) {
            throw new Error(`Failed to generate signed URL: ${signedUrlError?.message}`)
        }

        const videoUrl = signedUrlData.signedUrl
        console.log(`Signed URL generated`)

        // Use hardcoded credentials
        const credentials: Credentials = {
            youtube: {
                clientId: YOUTUBE_CLIENT_ID,
                clientSecret: YOUTUBE_CLIENT_SECRET,
                refreshToken: YOUTUBE_REFRESH_TOKEN,
            },
            instagram: {
                accessToken: INSTAGRAM_ACCESS_TOKEN,
                accountId: INSTAGRAM_ACCOUNT_ID,
            }
        }

        // Results object
        const results = {
            youtube: 'skipped' as string,
            youtube_video_id: null as string | null,
            youtube_error: null as string | null,
            instagram: 'skipped' as string,
            instagram_media_id: null as string | null,
            instagram_error: null as string | null,
            file_deleted: false,
        }

        // Upload to YouTube
        if (credentials.youtube?.clientId && credentials.youtube?.refreshToken) {
            console.log('Starting YouTube upload...')
            try {
                const ytAccessToken = await getYouTubeAccessToken(
                    credentials.youtube.clientId,
                    credentials.youtube.clientSecret,
                    credentials.youtube.refreshToken
                )
                const ytResult = await uploadToYouTube(ytAccessToken, videoUrl, caption)
                results.youtube = ytResult.success ? 'success' : 'failed'
                results.youtube_video_id = ytResult.videoId || null
                results.youtube_error = ytResult.error || null
            } catch (error: unknown) {
                results.youtube = 'failed'
                results.youtube_error = error instanceof Error ? error.message : String(error)
            }
        } else {
            console.log('YouTube credentials not configured, skipping...')
        }

        // Upload to Instagram
        if (credentials.instagram?.accessToken && credentials.instagram?.accountId) {
            console.log('Starting Instagram upload...')
            const igResult = await uploadToInstagram(
                credentials.instagram.accessToken,
                credentials.instagram.accountId,
                videoUrl,
                caption
            )
            results.instagram = igResult.success ? 'success' : 'failed'
            results.instagram_media_id = igResult.mediaId || null
            results.instagram_error = igResult.error || null
        } else {
            console.log('Instagram credentials not configured, skipping...')
        }

        // Cleanup: Delete video from storage
        try {
            const { error: deleteError } = await supabase.storage
                .from('temp_video_queue')
                .remove([video_filename])

            if (deleteError) {
                console.error('Failed to delete video:', deleteError)
            } else {
                results.file_deleted = true
                console.log('Video deleted from storage')
            }
        } catch (error: unknown) {
            console.error('Cleanup error:', error)
        }

        // Log the upload attempt
        try {
            await supabase.from('upload_logs').insert({
                user_id,
                video_filename,
                caption,
                youtube_status: results.youtube,
                youtube_video_id: results.youtube_video_id,
                instagram_status: results.instagram,
                instagram_media_id: results.instagram_media_id,
                error_message: results.youtube_error || results.instagram_error || null,
            })
        } catch (error: unknown) {
            console.error('Failed to log upload:', error)
        }

        return new Response(
            JSON.stringify(results),
            { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
    } catch (error: unknown) {
        console.error('Edge function error:', error)
        const errorMessage = error instanceof Error ? error.message : String(error)
        return new Response(
            JSON.stringify({ error: errorMessage }),
            { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
    }
})
