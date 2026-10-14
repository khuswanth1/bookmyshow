import { inr } from '../../lib/format'

const slugify = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
const yn = (v) => (v ? 'Yes' : 'No')

export const RESOURCES = {
  movies: {
    path: 'movies', title: 'Movies', singular: 'movie',
    columns: [{ header: 'Title', key: 'title' }, { header: 'Release', key: 'release_date' }, { header: 'Cert', key: 'certificate' }, { header: 'Languages', render: (r) => r.languages.map((l) => l.name).join(', ') },
      { header: 'Rating', render: (r) => (Number(r.rating_avg) > 0 ? `${r.rating_avg}${r.rating_count ? ` (${r.rating_count})` : ''}` : '–') }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [
      { key: 'title', label: 'Title', required: true, wide: true }, { key: 'synopsis', label: 'Synopsis', type: 'textarea' },
      { key: 'duration_min', label: 'Duration (min)', type: 'number', required: true, default: 120 }, { key: 'certificate', label: 'Certificate', type: 'select', options: ['U', 'UA', 'A', 'S'], default: 'UA' },
      { key: 'release_date', label: 'Release date', type: 'date', required: true }, { key: 'rating_avg', label: 'Rating (0-10)', type: 'number', default: 0, hint: 'Starting rating; replaced by the average of real user votes once people rate' }, { key: 'trailer_youtube_id', label: 'Trailer YouTube ID', optional: true },
      { key: 'poster_url', label: 'Poster URL (licensed only)', optional: true, wide: true }, { key: 'color_a', label: 'Gradient A', type: 'color', default: '#1f2937' }, { key: 'color_b', label: 'Gradient B', type: 'color', default: '#e11d48' },
      { key: 'genre_ids', label: 'Genres', type: 'multiselect', options: 'genres', fromRecord: (r) => r.genres.map((g) => g.id) },
      { key: 'language_ids', label: 'Languages', type: 'multiselect', options: 'languages', fromRecord: (r) => r.languages.map((g) => g.id) },
      { key: 'cast_members', label: 'Cast', type: 'pairs' }, { key: 'crew', label: 'Crew', type: 'pairs' }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true },
    ],
  },
  venues: {
    path: 'venues', title: 'Cinemas & venues', singular: 'venue',
    columns: [{ header: 'Name', key: 'name' }, { header: 'Type', key: 'type' }, { header: 'Chain', render: (r) => r.chain || '–' }, { header: 'City', render: (r) => r.city.name }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [
      { key: 'name', label: 'Name', required: true, wide: true }, { key: 'type', label: 'Type', type: 'select', options: ['cinema', 'venue'], default: 'cinema' },
      { key: 'chain', label: 'Chain / brand (regional cinemas)', optional: true }, { key: 'city_id', label: 'City', type: 'select', options: 'cities', numeric: true, required: true },
      { key: 'address', label: 'Address', required: true, wide: true }, { key: 'lat', label: 'Latitude', type: 'number', optional: true }, { key: 'lng', label: 'Longitude', type: 'number', optional: true },
      { key: 'amenities', label: 'Amenities', type: 'tags' }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true },
    ],
  },
  cities: {
    path: 'cities', title: 'Cities', singular: 'city',
    columns: [{ header: 'Name', key: 'name' }, { header: 'State', key: 'state' }, { header: 'Country', key: 'country' }, { header: 'Region', key: 'region' }, { header: 'Popular', render: (r) => yn(r.is_popular) }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [
      { key: 'name', label: 'Name', required: true }, { key: 'slug', label: 'Slug', required: true, hint: 'lowercase-with-dashes' }, { key: 'state', label: 'State / province', optional: true },
      { key: 'country', label: 'Country', default: 'India' }, { key: 'region', label: 'Region', type: 'select', options: ['india', 'international'], default: 'india' },
      { key: 'lat', label: 'Latitude', type: 'number', optional: true }, { key: 'lng', label: 'Longitude', type: 'number', optional: true },
      { key: 'is_popular', label: 'Popular', type: 'checkbox' }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true },
    ],
  },
  genres: { path: 'genres', title: 'Genres', singular: 'genre', columns: ['name', 'slug'], fields: [{ key: 'name', label: 'Name', required: true }, { key: 'slug', label: 'Slug', required: true }] },
  languages: {
    path: 'languages', title: 'Languages', singular: 'language', columns: [{ header: 'Name', key: 'name' }, { header: 'Code', key: 'code' }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [{ key: 'name', label: 'Name', required: true }, { key: 'code', label: 'ISO code', required: true }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true }],
  },
  categories: {
    path: 'categories', title: 'Event categories', singular: 'category', columns: [{ header: 'Section', key: 'section' }, { header: 'Name', key: 'name' }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [{ key: 'section', label: 'Section', type: 'select', options: ['events', 'plays', 'sports', 'activities'], default: 'events' }, { key: 'name', label: 'Name', required: true }, { key: 'slug', label: 'Slug', required: true }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true }],
  },
  coupons: {
    path: 'coupons', title: 'Coupons & offers', singular: 'coupon',
    columns: [{ header: 'Code', render: (r) => <span className="font-mono font-bold">{r.code}</span> }, { header: 'Title', key: 'title' }, { header: 'Kind', key: 'kind' },
      { header: 'Discount', render: (r) => (r.discount_type === 'percent' ? `${r.value}%` : inr(r.value)) }, { header: 'Used', render: (r) => `${r.used_count}${r.usage_limit ? `/${r.usage_limit}` : ''}` }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [
      { key: 'code', label: 'Code', required: true }, { key: 'title', label: 'Title', required: true }, { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'kind', label: 'Kind', type: 'select', options: ['general', 'bank', 'corporate'], default: 'general' }, { key: 'bank_name', label: 'Bank (for bank offers)', optional: true },
      { key: 'discount_type', label: 'Discount type', type: 'select', options: ['percent', 'flat'], default: 'percent' }, { key: 'value', label: 'Value (% or paise for flat)', type: 'number', required: true, hint: 'Flat: enter paise, e.g. 5000 = ₹50' },
      { key: 'max_discount_paise', label: 'Max discount (paise)', type: 'number', optional: true }, { key: 'min_order_paise', label: 'Min order (paise)', type: 'number', default: 0 },
      { key: 'applies_to', label: 'Applies to', type: 'select', options: ['all', 'movie', 'event'], default: 'all' }, { key: 'usage_limit', label: 'Total usage limit', type: 'number', optional: true }, { key: 'per_user_limit', label: 'Per-user limit', type: 'number', default: 1 },
      { key: 'ends_at', label: 'Valid until', type: 'datetime', optional: true }, { key: 'is_public', label: 'Show on Offers page', type: 'checkbox', default: true }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true },
    ],
  },
  videos: {
    path: 'videos', title: 'Stream videos', singular: 'video',
    columns: [{ header: 'Title', key: 'title' }, { header: 'Year', key: 'year' }, { header: 'License', key: 'license' }, { header: 'Featured', render: (r) => yn(r.is_featured) }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [
      { key: 'title', label: 'Title', required: true, wide: true }, { key: 'description', label: 'Description', type: 'textarea' }, { key: 'video_url', label: 'Video URL (mp4/webm)', required: true, wide: true },
      { key: 'license', label: 'License (required for redistribution)', required: true }, { key: 'attribution', label: 'Attribution', required: true }, { key: 'source_url', label: 'Source URL', optional: true },
      { key: 'year', label: 'Year', type: 'number', optional: true }, { key: 'duration_sec', label: 'Duration (sec)', type: 'number', default: 0 },
      { key: 'language_id', label: 'Language', type: 'select', options: 'languages', numeric: true, optional: true, fromRecord: (r) => r.language?.id },
      { key: 'genre_ids', label: 'Genres', type: 'multiselect', options: 'genres', fromRecord: (r) => r.genres.map((g) => g.id) },
      { key: 'color_a', label: 'Gradient A', type: 'color', default: '#0f172a' }, { key: 'color_b', label: 'Gradient B', type: 'color', default: '#6366f1' },
      { key: 'is_featured', label: 'Featured', type: 'checkbox' }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true },
    ],
  },
  faqs: {
    path: 'faqs', title: 'FAQs', singular: 'FAQ', columns: [{ header: 'Category', key: 'category' }, { header: 'Question', key: 'question' }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [{ key: 'category', label: 'Category', default: 'General' }, { key: 'sort_order', label: 'Order', type: 'number', default: 0 }, { key: 'question', label: 'Question', required: true, wide: true }, { key: 'answer', label: 'Answer', type: 'textarea', required: true }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true }],
  },
  initiatives: {
    path: 'initiatives', title: 'Social initiatives', singular: 'initiative',
    columns: [{ header: 'Title', key: 'title' }, { header: 'Partner', key: 'partner_name' }, { header: 'Donation', render: (r) => inr(r.amount_paise) }, { header: 'Active', render: (r) => yn(r.is_active) }],
    fields: [{ key: 'title', label: 'Title', required: true, wide: true }, { key: 'description', label: 'Description', type: 'textarea' }, { key: 'partner_name', label: 'Partner organisation' }, { key: 'amount_paise', label: 'Donation per booking (₹)', type: 'paise', default: 10 }, { key: 'is_active', label: 'Active', type: 'checkbox', default: true }],
  },
}
export { slugify }
