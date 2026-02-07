import { useState, useRef } from 'react'
import {
    Upload,
    Video,
    FileVideo,
    X,
    Send,
    CheckCircle2,
    Circle,
    Loader2,
    AlertCircle,
    Youtube,
    Instagram,
    Trash2,
    Terminal
} from 'lucide-react'
import { supabase, isSupabaseConfigured } from '../lib/supabase'

const UPLOAD_STEPS = [
    { id: 'upload', label: 'Uploading to Storage', icon: Upload },
    { id: 'process', label: 'Processing Edge Function', icon: FileVideo },
    { id: 'youtube', label: 'Publishing to YouTube', icon: Youtube },
    { id: 'instagram', label: 'Publishing to Instagram', icon: Instagram },
    { id: 'cleanup', label: 'Cleaning up', icon: Trash2 }
]

export default function Dashboard() {
    const fileInputRef = useRef(null)
    const [file, setFile] = useState(null)
    const [caption, setCaption] = useState('')
    const [isUploading, setIsUploading] = useState(false)
    const [currentStep, setCurrentStep] = useState(-1)
    const [stepStatuses, setStepStatuses] = useState({})
    const [logs, setLogs] = useState([])
    const [dragActive, setDragActive] = useState(false)

    const addLog = (message, type = 'info') => {
        const timestamp = new Date().toLocaleTimeString()
        setLogs(prev => [...prev, { timestamp, message, type }])
    }

    const handleDrag = (e) => {
        e.preventDefault()
        e.stopPropagation()
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true)
        } else if (e.type === 'dragleave') {
            setDragActive(false)
        }
    }

    const handleDrop = (e) => {
        e.preventDefault()
        e.stopPropagation()
        setDragActive(false)

        const droppedFile = e.dataTransfer.files[0]
        validateAndSetFile(droppedFile)
    }

    const validateAndSetFile = (selectedFile) => {
        if (!selectedFile) return

        if (!selectedFile.type.includes('mp4')) {
            addLog('Error: Only MP4 files are supported', 'error')
            return
        }

        const maxSize = 50 * 1024 * 1024
        if (selectedFile.size > maxSize) {
            addLog(`Error: File size exceeds 50MB limit (${(selectedFile.size / 1024 / 1024).toFixed(2)}MB)`, 'error')
            return
        }

        setFile(selectedFile)
        addLog(`File selected: ${selectedFile.name} (${(selectedFile.size / 1024 / 1024).toFixed(2)}MB)`, 'success')
    }

    const handleFileSelect = (e) => {
        validateAndSetFile(e.target.files[0])
    }

    const removeFile = () => {
        setFile(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
    }

    const updateStepStatus = (stepId, status) => {
        setStepStatuses(prev => ({ ...prev, [stepId]: status }))
        setCurrentStep(UPLOAD_STEPS.findIndex(s => s.id === stepId))
    }

    const handleUpload = async () => {
        if (!file || !caption.trim()) {
            addLog('Error: Please select a file and enter a caption', 'error')
            return
        }

        if (!isSupabaseConfigured || !supabase) {
            addLog('Error: Supabase is not configured. Please add environment variables.', 'error')
            return
        }

        setIsUploading(true)
        setStepStatuses({})
        setLogs([])

        try {
            updateStepStatus('upload', 'loading')
            addLog('Uploading video to Supabase Storage...')

            const filename = `${Date.now()}_${file.name}`
            const { error: uploadError } = await supabase.storage
                .from('temp_video_queue')
                .upload(filename, file)

            if (uploadError) throw new Error(`Storage upload failed: ${uploadError.message}`)

            updateStepStatus('upload', 'success')
            addLog('Video uploaded to storage successfully', 'success')

            updateStepStatus('process', 'loading')
            addLog('Calling publish-video Edge Function...')

            const { data: { user } } = await supabase.auth.getUser()
            if (!user) throw new Error('User not authenticated')

            const { data, error } = await supabase.functions.invoke('publish-video', {
                body: {
                    video_filename: filename,
                    caption: caption.trim(),
                    user_id: user.id
                }
            })

            if (error) throw new Error(`Edge Function error: ${error.message}`)

            updateStepStatus('process', 'success')
            addLog('Edge Function processing complete', 'success')

            if (data?.youtube === 'success') {
                updateStepStatus('youtube', 'success')
                addLog('Video published to YouTube Shorts!', 'success')
            } else {
                updateStepStatus('youtube', 'error')
                addLog(`YouTube upload failed: ${data?.youtube_error || 'Unknown error'}`, 'error')
            }

            if (data?.instagram === 'success') {
                updateStepStatus('instagram', 'success')
                addLog('Video published to Instagram Reels!', 'success')
            } else {
                updateStepStatus('instagram', 'error')
                addLog(`Instagram upload failed: ${data?.instagram_error || 'Unknown error'}`, 'error')
            }

            if (data?.file_deleted) {
                updateStepStatus('cleanup', 'success')
                addLog('Temporary file cleaned up', 'success')
            } else {
                updateStepStatus('cleanup', 'error')
                addLog('Warning: Cleanup may have failed', 'warning')
            }

            if (data?.youtube === 'success' && data?.instagram === 'success') {
                addLog('🎉 Video successfully published to both platforms!', 'success')
            }

            setFile(null)
            setCaption('')
            if (fileInputRef.current) fileInputRef.current.value = ''

        } catch (error) {
            console.error('Upload error:', error)
            addLog(`Error: ${error.message}`, 'error')

            const currentStepId = UPLOAD_STEPS[currentStep]?.id
            if (currentStepId) {
                updateStepStatus(currentStepId, 'error')
            }
        } finally {
            setIsUploading(false)
        }
    }

    const getStepIcon = (step) => {
        const status = stepStatuses[step.id]
        const Icon = step.icon

        if (status === 'loading') {
            return <Loader2 style={{ width: 20, height: 20, color: '#818cf8' }} className="animate-spin" />
        } else if (status === 'success') {
            return <CheckCircle2 style={{ width: 20, height: 20, color: '#4ade80' }} />
        } else if (status === 'error') {
            return <AlertCircle style={{ width: 20, height: 20, color: '#f87171' }} />
        } else {
            return <Icon style={{ width: 20, height: 20, color: '#6b7280' }} />
        }
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
            {/* Header */}
            <div>
                <h2 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '8px' }}>Upload Dashboard</h2>
                <p style={{ color: '#9ca3af' }}>Upload a vertical video to publish to YouTube Shorts and Instagram Reels.</p>
            </div>

            {/* Warning Banner */}
            {!isSupabaseConfigured && (
                <div className="warning-banner" style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                    <AlertCircle style={{ width: 22, height: 22, color: '#fbbf24', flexShrink: 0, marginTop: 2 }} />
                    <div>
                        <p style={{ fontWeight: 600, color: '#fcd34d', marginBottom: '6px' }}>Supabase Not Configured</p>
                        <p style={{ color: '#fde68a', opacity: 0.8, fontSize: '0.9rem' }}>
                            Create a <code>.env</code> file with your Supabase credentials:
                        </p>
                        <pre style={{
                            marginTop: '10px',
                            padding: '10px 14px',
                            background: 'rgba(0,0,0,0.25)',
                            borderRadius: '8px',
                            color: '#fde68a',
                            opacity: 0.7,
                            fontSize: '0.8rem'
                        }}>
                            VITE_SUPABASE_URL=your_url{'\n'}VITE_SUPABASE_ANON_KEY=your_key
                        </pre>
                    </div>
                </div>
            )}

            {/* Main Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '24px' }}>
                {/* Left Column - Upload */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    {/* Drop Zone */}
                    <div
                        className={`drop-zone ${dragActive ? 'active' : ''} ${file ? 'has-file' : ''}`}
                        onDragEnter={handleDrag}
                        onDragLeave={handleDrag}
                        onDragOver={handleDrag}
                        onDrop={handleDrop}
                        style={{ minHeight: '220px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                        {file ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '20px', width: '100%', padding: '0 16px' }}>
                                <div className="icon-box icon-box-lg" style={{ background: 'rgba(34, 197, 94, 0.15)' }}>
                                    <Video style={{ width: 32, height: 32, color: '#4ade80' }} />
                                </div>
                                <div style={{ flex: 1 }}>
                                    <p style={{ fontWeight: 600, color: '#f5f5f7', fontSize: '1.05rem' }}>{file.name}</p>
                                    <p style={{ color: '#9ca3af', fontSize: '0.9rem', marginTop: '4px' }}>{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                                </div>
                                <button
                                    onClick={removeFile}
                                    disabled={isUploading}
                                    style={{
                                        padding: '10px',
                                        borderRadius: '10px',
                                        background: 'rgba(239, 68, 68, 0.15)',
                                        border: '1px solid rgba(239, 68, 68, 0.3)',
                                        color: '#f87171',
                                        opacity: isUploading ? 0.5 : 1
                                    }}
                                >
                                    <X style={{ width: 20, height: 20 }} />
                                </button>
                            </div>
                        ) : (
                            <div style={{ textAlign: 'center' }}>
                                <div className="icon-box icon-box-lg" style={{
                                    background: 'rgba(99, 102, 241, 0.15)',
                                    margin: '0 auto 20px'
                                }}>
                                    <Upload style={{ width: 32, height: 32, color: '#818cf8' }} />
                                </div>
                                <p style={{ fontSize: '1.15rem', fontWeight: 600, color: '#f5f5f7', marginBottom: '8px' }}>
                                    Drop your video here
                                </p>
                                <p style={{ color: '#9ca3af', marginBottom: '20px' }}>or click to browse</p>
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept="video/mp4"
                                    onChange={handleFileSelect}
                                    style={{ display: 'none' }}
                                    id="video-upload"
                                />
                                <label htmlFor="video-upload" className="btn-primary" style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '8px',
                                    cursor: 'pointer'
                                }}>
                                    <FileVideo style={{ width: 20, height: 20 }} />
                                    <span>Select MP4 File</span>
                                </label>
                                <p style={{ color: '#6b7280', fontSize: '0.85rem', marginTop: '20px' }}>
                                    Maximum file size: 50MB • MP4 only • Under 60 seconds
                                </p>
                            </div>
                        )}
                    </div>

                    {/* Caption Input */}
                    <div className="card">
                        <label style={{
                            display: 'block',
                            fontWeight: 500,
                            color: '#d1d5db',
                            marginBottom: '12px',
                            fontSize: '0.95rem'
                        }}>
                            Title / Caption
                        </label>
                        <textarea
                            value={caption}
                            onChange={(e) => setCaption(e.target.value)}
                            placeholder="Enter a caption for your video (used for both platforms)"
                            rows={3}
                            className="input-field"
                            style={{ resize: 'none' }}
                        />
                        <p style={{ color: '#6b7280', fontSize: '0.85rem', marginTop: '10px' }}>
                            {caption.length} characters
                        </p>
                    </div>

                    {/* Upload Button */}
                    <button
                        onClick={handleUpload}
                        disabled={!file || !caption.trim() || isUploading}
                        className={file && caption.trim() && !isUploading ? 'btn-gradient pulse-glow' : ''}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '12px',
                            padding: '18px 32px',
                            borderRadius: '14px',
                            fontSize: '1.05rem',
                            fontWeight: 600,
                            border: 'none',
                            color: !file || !caption.trim() || isUploading ? '#6b7280' : 'white',
                            background: !file || !caption.trim()
                                ? '#1f2937'
                                : isUploading
                                    ? 'rgba(99, 102, 241, 0.4)'
                                    : undefined,
                            cursor: !file || !caption.trim() || isUploading ? 'not-allowed' : 'pointer'
                        }}
                    >
                        {isUploading ? (
                            <>
                                <Loader2 style={{ width: 24, height: 24 }} className="animate-spin" />
                                <span>Publishing...</span>
                            </>
                        ) : (
                            <>
                                <Send style={{ width: 24, height: 24 }} />
                                <span>Publish to All Platforms</span>
                            </>
                        )}
                    </button>
                </div>

                {/* Right Column - Progress & Logs */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    {/* Progress Steps */}
                    <div className="card">
                        <h3 style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            fontSize: '1.1rem',
                            fontWeight: 600,
                            marginBottom: '18px'
                        }}>
                            <Circle style={{ width: 20, height: 20, color: '#818cf8' }} />
                            Progress
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                            {UPLOAD_STEPS.map((step) => (
                                <div
                                    key={step.id}
                                    className={`progress-step ${stepStatuses[step.id] || ''}`}
                                >
                                    {getStepIcon(step)}
                                    <span style={{
                                        fontSize: '0.9rem',
                                        color: stepStatuses[step.id] ? '#f5f5f7' : '#6b7280'
                                    }}>
                                        {step.label}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Log Console */}
                    <div className="card" style={{ flex: 1 }}>
                        <h3 style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            fontSize: '1.1rem',
                            fontWeight: 600,
                            marginBottom: '18px'
                        }}>
                            <Terminal style={{ width: 20, height: 20, color: '#818cf8' }} />
                            Console
                        </h3>
                        <div className="console" style={{
                            padding: '16px',
                            height: '240px',
                            overflowY: 'auto'
                        }}>
                            {logs.length === 0 ? (
                                <p style={{ color: '#4b5563' }}>Waiting for upload...</p>
                            ) : (
                                logs.map((log, index) => (
                                    <div key={index} style={{ display: 'flex', gap: '10px', marginBottom: '4px' }}>
                                        <span style={{ color: '#4b5563' }}>[{log.timestamp}]</span>
                                        <span style={{
                                            color: log.type === 'error' ? '#f87171' :
                                                log.type === 'success' ? '#4ade80' :
                                                    log.type === 'warning' ? '#fbbf24' : '#d1d5db'
                                        }}>
                                            {log.message}
                                        </span>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
