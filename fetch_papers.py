import requests
import xml.etree.ElementTree as ET

def fetch_arxiv_papers():
    url = (
        'http://export.arxiv.org/api/query?search_query=cat:cs.AI'
        '&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending'
    )
    response = requests.get(url)
    root = ET.fromstring(response.text)
# the below is used for parsing
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    papers = []

    for entry in root.findall('atom:entry', ns):
        title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
        
        # Extract authors
        authors = [
            author.find('atom:name', ns).text
            for author in entry.findall('atom:author', ns)
        ]
        authors_str = ', '.join(authors)

        # Extract published date
        published = entry.find('atom:published', ns).text

        # Extract summary
        summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')

        # Extract HTML link
        link = None
        for link_elem in entry.findall('atom:link', ns):
            if link_elem.attrib.get('type') == 'text/html':
                link = link_elem.attrib['href']
                break

        papers.append({
            'title': title,
            'authors': authors_str,
            'published': published,
            'summary': summary,
            'link': link
        })

    return papers

# Example usage
if __name__ == '__main__':
    papers = fetch_arxiv_papers()
    for p in papers:
        print(f"Title: {p['title']}")
        print(f"Authors: {p['authors']}")
        print(f"Published: {p['published']}")
        print(f"Summary: {p['summary']}")
        print(f"Link: {p['link']}\n")
