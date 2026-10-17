import { getCollection, type CollectionEntry } from 'astro:content';

export type Entry = CollectionEntry<'guides' | 'news'>;

const byDate = (a: Entry, b: Entry) => b.data.publishDate.valueOf() - a.data.publishDate.valueOf();
const published = ({ data }: Entry) => !data.draft && data.publishDate <= new Date();

export const getGuides = async () => (await getCollection('guides', published)).sort(byDate);
export const getNews = async () => (await getCollection('news', published)).sort(byDate);
